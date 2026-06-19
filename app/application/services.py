from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.metrics import (
    generation_error_total,
    generation_success_total,
    generation_tokens_spent_total,
    generation_total,
    webhook_delivery_total,
)
from app.core.security import generate_api_key, hash_api_key
from app.domain.enums import DeliveryStatus, GenerationStatus, InputKind, MediaKind, TransactionKind
from app.infrastructure.http import CallbackClient
from app.infrastructure.persistence.models import GenerationTask, User, WebhookDelivery
from app.infrastructure.persistence.repositories import (
    BalanceRepository,
    DeliveryRepository,
    GenerationRepository,
    PaymentRepository,
    RateLimitRepository,
    UserRepository,
)
from app.infrastructure.providers.base import GenerationRequest, ProviderError
from app.infrastructure.providers.router import ProviderRouter

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AuthenticationError(Exception):
    pass


class BalanceError(Exception):
    pass


class NotFoundError(Exception):
    pass


class RetryableWebhookDeliveryError(Exception):
    pass


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def register_user(
        self, external_user_id: str, callback_url: str
    ) -> tuple[User, str]:
        api_key = generate_api_key()
        api_key_hash = hash_api_key(api_key)

        async with self.session_factory() as session:
            users = UserRepository(session)
            user = await users.get_by_external_user_id(external_user_id)

            if user is None:
                user = User(
                    external_user_id=external_user_id,
                    api_key_hash=api_key_hash,
                    callback_url=callback_url,
                )
                users.add(user)
            else:
                user.api_key_hash = api_key_hash
                user.callback_url = callback_url

            await session.commit()
            await session.refresh(user)
            return user, api_key

    async def authenticate(self, api_key: str) -> User:
        async with self.session_factory() as session:
            user = await UserRepository(session).get_by_api_key_hash(hash_api_key(api_key))
            if user is None:
                raise AuthenticationError("invalid API key")
            return user

    async def enforce_rate_limit(self, user_id: str) -> None:
        async with self.session_factory() as session:
            repo = RateLimitRepository(session)
            state = await repo.get_or_create_for_update(user_id)
            now = utcnow()
            blocked_until = as_aware_utc(state.blocked_until) if state.blocked_until else None
            window_started_at = as_aware_utc(state.window_started_at)

            if blocked_until and blocked_until > now:
                await session.rollback()
                raise BalanceError("rate limit exceeded, user is temporarily blocked")

            window_age = (now - window_started_at).total_seconds()
            if window_age >= self.settings.request_rate_window_seconds:
                state.requests_count = 0
                state.window_started_at = now
                state.blocked_until = None

            state.requests_count += 1
            if state.requests_count > self.settings.request_rate_limit:
                state.blocked_until = now.replace(microsecond=0) + self._block_delta()
                await session.commit()
                raise BalanceError("rate limit exceeded, user is blocked for 60 seconds")

            await session.commit()

    def _block_delta(self):
        return timedelta(seconds=self.settings.request_block_seconds)


class UserService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_user(self, user_id: str) -> User:
        async with self.session_factory() as session:
            user = await UserRepository(session).get_by_id(user_id)
            if user is None:
                raise NotFoundError("user not found")
            return user


class PaymentService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def top_up(self, external_user_id: str, amount: int, payload: dict) -> User:
        if amount <= 0:
            raise BalanceError("amount must be positive")

        async with self.session_factory() as session:
            users = UserRepository(session)
            balances = BalanceRepository(session)
            payments = PaymentRepository(session)

            user = await users.get_by_external_user_id(external_user_id)
            if user is None:
                raise NotFoundError("user not found")

            locked_user = await users.get_by_id_for_update(user.id)
            if locked_user is None:
                raise NotFoundError("user not found")

            locked_user.balance_tokens += amount
            payments.add_event(external_user_id, amount, payload)
            balances.add_transaction(
                user_id=locked_user.id,
                amount=amount,
                kind=TransactionKind.CREDIT,
                reference_id=None,
                metadata_json={"source": "payment_webhook"},
            )

            await session.commit()
            await session.refresh(locked_user)
            return locked_user


class GenerationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings

    async def create_generation(
        self,
        *,
        user_id: str,
        media_kind: MediaKind,
        input_kind: InputKind,
        prompt: str,
        source_image_url: str | None,
        callback_url: str | None,
    ) -> GenerationTask:
        price_key = f"{media_kind.value}:{input_kind.value}"
        reserved_tokens = self.settings.generation_prices[price_key]

        async with self.session_factory() as session:
            users = UserRepository(session)
            generations = GenerationRepository(session)

            user = await users.get_by_id_for_update(user_id)
            if user is None:
                raise NotFoundError("user not found")
            if user.available_tokens < reserved_tokens:
                raise BalanceError("insufficient balance")

            user.reserved_tokens += reserved_tokens
            generation = GenerationTask(
                id=str(uuid4()),
                user_id=user.id,
                media_kind=media_kind,
                input_kind=input_kind,
                prompt=prompt,
                source_image_url=source_image_url,
                callback_url=callback_url or user.callback_url,
                reserved_tokens=reserved_tokens,
            )
            generations.add(generation)

            generation_total.labels(
                media_kind=media_kind.value,
                input_kind=input_kind.value,
                status=GenerationStatus.CREATED.value,
            ).inc()

            await session.commit()
            await session.refresh(generation)
            return generation

    async def get_generation(self, user_id: str, generation_id: str) -> GenerationTask:
        async with self.session_factory() as session:
            generation = await GenerationRepository(session).get_for_user(generation_id, user_id)
            if generation is None:
                raise NotFoundError("generation not found")
            return generation

    async def mark_generation_queued(self, user_id: str, generation_id: str) -> GenerationTask:
        async with self.session_factory() as session:
            generation = await GenerationRepository(session).get_for_user(generation_id, user_id)
            if generation is None:
                raise NotFoundError("generation not found")
            if generation.status != GenerationStatus.CREATED:
                return generation

            generation.status = GenerationStatus.QUEUED
            generation_total.labels(
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
                status=GenerationStatus.QUEUED.value,
            ).inc()
            await session.commit()
            await session.refresh(generation)
            return generation

    async def mark_enqueue_failed(self, generation_id: str, error_message: str) -> None:
        async with self.session_factory() as session:
            generation = await session.get(GenerationTask, generation_id, with_for_update=True)
            if generation is None:
                return
            if generation.status in {GenerationStatus.COMPLETED, GenerationStatus.FAILED}:
                return

            user = await UserRepository(session).get_by_id_for_update(generation.user_id)
            if user is None:
                await session.rollback()
                return

            generation.status = GenerationStatus.FAILED
            generation.error_message = error_message
            user.reserved_tokens -= generation.reserved_tokens
            generation_total.labels(
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
                status=GenerationStatus.FAILED.value,
            ).inc()
            await session.commit()

    async def list_generations(self, user_id: str, limit: int = 50) -> list[GenerationTask]:
        async with self.session_factory() as session:
            return await GenerationRepository(session).list_for_user(user_id, limit=limit)


class GenerationWorkerService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider_router: ProviderRouter,
    ) -> None:
        self.session_factory = session_factory
        self.provider_router = provider_router

    async def process_generation(self, generation_id: str) -> str | None:
        async with self.session_factory() as session:
            generation = await session.get(GenerationTask, generation_id, with_for_update=True)
            if generation is None:
                await session.rollback()
                return None
            if generation.status not in {GenerationStatus.CREATED, GenerationStatus.QUEUED}:
                delivery = await DeliveryRepository(session).get_pending_by_generation_id(
                    generation.id
                )
                await session.rollback()
                return delivery.id if delivery else None
            generation.status = GenerationStatus.PROCESSING
            generation_total.labels(
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
                status=GenerationStatus.PROCESSING.value,
            ).inc()
            await session.commit()

        try:
            response = await self.provider_router.generate(
                GenerationRequest(
                    generation_id=generation.id,
                    prompt=generation.prompt,
                    media_kind=generation.media_kind,
                    input_kind=generation.input_kind,
                    source_image_url=generation.source_image_url,
                )
            )
        except ProviderError as exc:
            return await self._fail_generation(generation.id, str(exc))

        return await self._complete_generation(
            generation.id,
            response.provider_name,
            response.provider_task_id,
            response.result_url,
            response.payload,
        )

    async def _complete_generation(
        self,
        generation_id: str,
        provider_name: str,
        provider_task_id: str | None,
        result_url: str | None,
        payload: dict,
    ) -> str | None:
        async with self.session_factory() as session:
            generation = await session.get(GenerationTask, generation_id, with_for_update=True)
            if generation is None:
                return None

            user = await UserRepository(session).get_by_id_for_update(generation.user_id)
            if user is None:
                await session.rollback()
                return None

            generation.status = GenerationStatus.COMPLETED
            generation.provider_name = provider_name
            generation.provider_task_id = provider_task_id
            generation.result_url = result_url
            generation.result_payload = payload
            generation.error_message = None

            user.reserved_tokens -= generation.reserved_tokens
            user.balance_tokens -= generation.reserved_tokens
            BalanceRepository(session).add_transaction(
                user_id=user.id,
                amount=-generation.reserved_tokens,
                kind=TransactionKind.DEBIT,
                reference_id=generation.id,
                metadata_json={"reason": "generation_completed"},
            )

            generation_total.labels(
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
                status=GenerationStatus.COMPLETED.value,
            ).inc()
            generation_success_total.labels(
                provider=provider_name,
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
            ).inc()
            generation_tokens_spent_total.labels(
                provider=provider_name,
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
            ).inc(generation.reserved_tokens)

            delivery_id = await self._schedule_callback(session, generation)
            await session.commit()
            return delivery_id

    async def _fail_generation(self, generation_id: str, error_message: str) -> str | None:
        async with self.session_factory() as session:
            generation = await session.get(GenerationTask, generation_id, with_for_update=True)
            if generation is None:
                return None

            user = await UserRepository(session).get_by_id_for_update(generation.user_id)
            if user is None:
                await session.rollback()
                return None

            generation.status = GenerationStatus.FAILED
            generation.error_message = error_message
            user.reserved_tokens -= generation.reserved_tokens

            provider_name = generation.provider_name or "fallback"
            generation_total.labels(
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
                status=GenerationStatus.FAILED.value,
            ).inc()
            generation_error_total.labels(
                provider=provider_name,
                media_kind=generation.media_kind.value,
                input_kind=generation.input_kind.value,
            ).inc()

            delivery_id = await self._schedule_callback(session, generation)
            await session.commit()
            logger.error("generation %s failed: %s", generation_id, error_message)
            return delivery_id

    async def _schedule_callback(
        self, session: AsyncSession, generation: GenerationTask
    ) -> str | None:
        if not generation.callback_url:
            return None

        payload = {
            "generation_id": generation.id,
            "status": generation.status.value,
            "provider": generation.provider_name,
            "result_url": generation.result_url,
            "result": generation.result_payload,
            "error_message": generation.error_message,
        }
        delivery = WebhookDelivery(
            id=str(uuid4()),
            generation_id=generation.id,
            target_url=generation.callback_url,
            payload=payload,
        )
        DeliveryRepository(session).add(delivery)
        return delivery.id


class DeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        callback_client: CallbackClient,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.callback_client = callback_client

    async def deliver_webhook(self, delivery_id: str) -> bool:
        async with self.session_factory() as session:
            delivery = await session.get(WebhookDelivery, delivery_id, with_for_update=True)
            if delivery is None or delivery.status != DeliveryStatus.PENDING:
                await session.rollback()
                return False

            try:
                response = await self.callback_client.post_json(
                    delivery.target_url,
                    delivery.payload,
                    attempt_number=delivery.attempts + 1,
                )
                response.raise_for_status()
            except Exception as exc:
                delivery.attempts += 1
                delivery.last_error = str(exc)
                if delivery.attempts >= self.settings.webhook_max_attempts:
                    delivery.status = DeliveryStatus.FAILED
                    webhook_delivery_total.labels(status=DeliveryStatus.FAILED.value).inc()
                else:
                    webhook_delivery_total.labels(status="retry").inc()
                await session.commit()
                if delivery.status == DeliveryStatus.PENDING:
                    raise RetryableWebhookDeliveryError(str(exc)) from exc
                return False

            delivery.status = DeliveryStatus.DELIVERED
            delivery.attempts += 1
            delivery.delivered_at = utcnow()
            delivery.last_error = None
            webhook_delivery_total.labels(status=DeliveryStatus.DELIVERED.value).inc()
            await session.commit()
            return True
