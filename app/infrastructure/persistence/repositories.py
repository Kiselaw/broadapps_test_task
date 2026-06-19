from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DeliveryStatus, TransactionKind
from app.infrastructure.persistence.models import (
    BalanceTransaction,
    GenerationTask,
    PaymentEvent,
    ProviderHealth,
    RateLimitState,
    User,
    WebhookDelivery,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_external_user_id(self, external_user_id: str) -> User | None:
        return await self.session.scalar(
            select(User).where(User.external_user_id == external_user_id)
        )

    async def get_by_api_key_hash(self, api_key_hash: str) -> User | None:
        return await self.session.scalar(select(User).where(User.api_key_hash == api_key_hash))

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_id_for_update(self, user_id: str) -> User | None:
        statement: Select[tuple[User]] = select(User).where(User.id == user_id).with_for_update()
        return await self.session.scalar(statement)

    def add(self, user: User) -> None:
        self.session.add(user)


class BalanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_transaction(
        self,
        *,
        user_id: str,
        amount: int,
        kind: TransactionKind,
        reference_id: str | None,
        metadata_json: dict | None = None,
    ) -> None:
        self.session.add(
            BalanceTransaction(
                user_id=user_id,
                amount=amount,
                kind=kind,
                reference_id=reference_id,
                metadata_json=metadata_json or {},
            )
        )


class GenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, generation: GenerationTask) -> None:
        self.session.add(generation)

    async def get_for_user(self, generation_id: str, user_id: str) -> GenerationTask | None:
        statement = select(GenerationTask).where(
            GenerationTask.id == generation_id,
            GenerationTask.user_id == user_id,
        )
        return await self.session.scalar(statement)

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[GenerationTask]:
        statement = (
            select(GenerationTask)
            .where(GenerationTask.user_id == user_id)
            .order_by(GenerationTask.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_event(self, external_user_id: str, amount: int, payload: dict) -> None:
        self.session.add(
            PaymentEvent(external_user_id=external_user_id, amount=amount, payload=payload)
        )


class DeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, delivery: WebhookDelivery) -> None:
        self.session.add(delivery)

    async def get_pending_by_generation_id(self, generation_id: str) -> WebhookDelivery | None:
        statement = select(WebhookDelivery).where(
            WebhookDelivery.generation_id == generation_id,
            WebhookDelivery.status == DeliveryStatus.PENDING,
        )
        return await self.session.scalar(statement)


class RateLimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_for_update(self, user_id: str) -> RateLimitState:
        state = await self.session.get(RateLimitState, user_id, with_for_update=True)
        if state is None:
            state = RateLimitState(user_id=user_id)
            self.session.add(state)
            await self.session.flush()
        return state


class ProviderHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_for_update(self, provider_name: str) -> ProviderHealth:
        state = await self.session.get(ProviderHealth, provider_name, with_for_update=True)
        if state is None:
            state = ProviderHealth(provider_name=provider_name, consecutive_failures=0)
            self.session.add(state)
            await self.session.flush()
        return state

    async def is_available(self, provider_name: str) -> bool:
        state = await self.session.get(ProviderHealth, provider_name)
        if state is None or state.available_after is None:
            return True

        available_after = state.available_after
        if available_after.tzinfo is None:
            available_after = available_after.replace(tzinfo=UTC)

        return available_after <= utcnow()
