from __future__ import annotations

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.domain.enums import InputKind, MediaKind
from app.infrastructure.providers.base import (
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderError,
    ProviderUnavailableError,
)


class FalGenerationProvider(GenerationProvider):
    name = "fal"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        if self.settings.test_fal:
            return self._generate_test_response(request)

        if not self.settings.fal_api_key:
            raise ProviderUnavailableError("FAL_API_KEY is not configured")

        try:
            import os

            import fal_client
        except ImportError as exc:
            raise ProviderUnavailableError("fal-client dependency is not installed") from exc

        os.environ["FAL_KEY"] = self.settings.fal_api_key
        model_id = self._resolve_model(request.media_kind, request.input_kind)
        arguments = self._build_arguments(request)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=4),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    handler = await fal_client.submit_async(model_id, arguments=arguments)
                    result = await handler.get_async()
        except Exception as exc:  # pragma: no cover - depends on external provider
            raise ProviderError(str(exc)) from exc

        result_url = self._extract_result_url(request.media_kind, result)
        return GenerationResponse(
            provider_name=self.name,
            provider_task_id=getattr(handler, "request_id", None),
            result_url=result_url,
            payload=result,
        )

    def _generate_test_response(self, request: GenerationRequest) -> GenerationResponse:
        if "force-fail" in request.prompt.lower():
            raise ProviderError("fal test provider forced failure")

        extension = "mp4" if request.media_kind == MediaKind.VIDEO else "png"
        url = f"{self.settings.test_fal_base_url}/{request.generation_id}.{extension}"
        payload = (
            {"images": [{"url": url}]}
            if request.media_kind == MediaKind.IMAGE
            else {"video": {"url": url}}
        )
        return GenerationResponse(
            provider_name=self.name,
            provider_task_id=f"fal-test-{request.generation_id}",
            result_url=url,
            payload={
                **payload,
                "test_mode": True,
                "input": self._build_arguments(request),
            },
        )

    def _resolve_model(self, media_kind: MediaKind, input_kind: InputKind) -> str:
        mapping = {
            (MediaKind.IMAGE, InputKind.TEXT): self.settings.fal_text_to_image_model,
            (MediaKind.IMAGE, InputKind.IMAGE): self.settings.fal_image_to_image_model,
            (MediaKind.VIDEO, InputKind.TEXT): self.settings.fal_text_to_video_model,
            (MediaKind.VIDEO, InputKind.IMAGE): self.settings.fal_image_to_video_model,
        }
        return mapping[(media_kind, input_kind)]

    @staticmethod
    def _extract_result_url(media_kind: MediaKind, payload: dict) -> str | None:
        if media_kind == MediaKind.IMAGE:
            images = payload.get("images") or []
            if images:
                return images[0].get("url")
            return None
        video = payload.get("video") or {}
        return video.get("url")

    @staticmethod
    def _build_arguments(request: GenerationRequest) -> dict:
        arguments = {"prompt": request.prompt}
        if request.media_kind == MediaKind.IMAGE and request.input_kind == InputKind.IMAGE:
            arguments["image_urls"] = [request.source_image_url]
        elif request.media_kind == MediaKind.VIDEO and request.input_kind == InputKind.IMAGE:
            arguments["image_url"] = request.source_image_url
        return arguments
