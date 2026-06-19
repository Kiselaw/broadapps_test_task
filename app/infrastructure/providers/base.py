from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import InputKind, MediaKind


class ProviderError(Exception):
    pass


class ProviderUnavailableError(ProviderError):
    pass


@dataclass(slots=True)
class GenerationRequest:
    generation_id: str
    prompt: str
    media_kind: MediaKind
    input_kind: InputKind
    source_image_url: str | None = None


@dataclass(slots=True)
class GenerationResponse:
    provider_name: str
    provider_task_id: str | None
    result_url: str | None
    payload: dict


class GenerationProvider:
    name: str

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError
