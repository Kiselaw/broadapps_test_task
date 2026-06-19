from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.infrastructure.persistence.repositories import ProviderHealthRepository
from app.infrastructure.providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderError,
)
from app.infrastructure.providers.fal import FalGenerationProvider
from app.infrastructure.providers.mock import MockGenerationProvider


def utcnow() -> datetime:
    return datetime.now(UTC)


class ProviderRouter:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.providers: dict[str, GenerationProvider] = {
            "fal": FalGenerationProvider(settings),
            "mock": MockGenerationProvider(settings),
        }

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        last_error: Exception | None = None

        for provider_name in self.settings.provider_chain:
            provider = self.providers.get(provider_name)
            if provider is None:
                continue
            if not await self._is_available(provider_name):
                continue

            try:
                response = await provider.generate(request)
            except ProviderError as exc:
                last_error = exc
                await self._mark_failure(provider_name)
                continue

            await self._mark_success(provider_name)
            return response

        raise ProviderError(str(last_error or "no providers available"))

    async def _is_available(self, provider_name: str) -> bool:
        async with self.session_factory() as session:
            return await ProviderHealthRepository(session).is_available(provider_name)

    async def _mark_failure(self, provider_name: str) -> None:
        async with self.session_factory() as session:
            state = await ProviderHealthRepository(session).get_or_create_for_update(provider_name)
            state.consecutive_failures += 1
            if state.consecutive_failures >= self.settings.provider_failure_threshold:
                state.available_after = utcnow() + timedelta(
                    seconds=self.settings.provider_cooldown_seconds
                )
            await session.commit()

    async def _mark_success(self, provider_name: str) -> None:
        async with self.session_factory() as session:
            state = await ProviderHealthRepository(session).get_or_create_for_update(provider_name)
            state.consecutive_failures = 0
            state.available_after = None
            await session.commit()
