import asyncio

from app.core.config import Settings
from app.domain.enums import MediaKind
from app.infrastructure.providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderError,
)


class MockGenerationProvider(GenerationProvider):
    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        await asyncio.sleep(self.settings.mock_provider_delay_seconds)
        if "force-fail" in request.prompt.lower():
            raise ProviderError("mock provider forced failure")

        extension = "mp4" if request.media_kind == MediaKind.VIDEO else "png"
        url = f"{self.settings.mock_provider_base_url}/{request.generation_id}.{extension}"
        if request.media_kind == MediaKind.IMAGE:
            payload = {"images": [{"url": url}]}
        else:
            payload = {"video": {"url": url}}

        return GenerationResponse(
            provider_name=self.name,
            provider_task_id=f"mock-{request.generation_id}",
            result_url=url,
            payload=payload,
        )
