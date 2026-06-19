from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.container import AppContainer
from app.domain.enums import InputKind, MediaKind
from app.infrastructure.persistence.models import User
from app.infrastructure.tasks.generation import enqueue_generation
from app.presentation.api.deps import get_container, get_current_user, map_service_error
from app.presentation.api.schemas import (
    GenerationCreateRequest,
    GenerationResponse,
    ImageToImageRequest,
)

router = APIRouter(prefix="/generations", tags=["generations"])


@router.post("/images/text-to-image", response_model=GenerationResponse)
async def create_text_to_image(
    payload: GenerationCreateRequest,
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> GenerationResponse:
    return await _create_generation(
        container=container,
        current_user=current_user,
        media_kind=MediaKind.IMAGE,
        input_kind=InputKind.TEXT,
        prompt=payload.prompt,
        source_image_url=None,
        callback_url=str(payload.callback_url) if payload.callback_url else None,
    )


@router.post("/images/image-to-image", response_model=GenerationResponse)
async def create_image_to_image(
    payload: ImageToImageRequest,
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> GenerationResponse:
    return await _create_generation(
        container=container,
        current_user=current_user,
        media_kind=MediaKind.IMAGE,
        input_kind=InputKind.IMAGE,
        prompt=payload.prompt,
        source_image_url=str(payload.source_image_url),
        callback_url=str(payload.callback_url) if payload.callback_url else None,
    )


@router.post("/videos/text-to-video", response_model=GenerationResponse)
async def create_text_to_video(
    payload: GenerationCreateRequest,
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> GenerationResponse:
    return await _create_generation(
        container=container,
        current_user=current_user,
        media_kind=MediaKind.VIDEO,
        input_kind=InputKind.TEXT,
        prompt=payload.prompt,
        source_image_url=None,
        callback_url=str(payload.callback_url) if payload.callback_url else None,
    )


@router.post("/videos/image-to-video", response_model=GenerationResponse)
async def create_image_to_video(
    payload: ImageToImageRequest,
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> GenerationResponse:
    return await _create_generation(
        container=container,
        current_user=current_user,
        media_kind=MediaKind.VIDEO,
        input_kind=InputKind.IMAGE,
        prompt=payload.prompt,
        source_image_url=str(payload.source_image_url),
        callback_url=str(payload.callback_url) if payload.callback_url else None,
    )


@router.get("", response_model=list[GenerationResponse])
async def list_generations(
    limit: int = Query(default=50, ge=1, le=100),
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> list[GenerationResponse]:
    generations = await container.generation_service.list_generations(current_user.id, limit)
    return [GenerationResponse.model_validate(item) for item in generations]


@router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation(
    generation_id: str,
    container: AppContainer = Depends(get_container),
    current_user: User = Depends(get_current_user),
) -> GenerationResponse:
    try:
        generation = await container.generation_service.get_generation(
            current_user.id, generation_id
        )
    except Exception as exc:  # pragma: no cover - mapped centrally
        raise map_service_error(exc) from exc

    return GenerationResponse.model_validate(generation)


async def _create_generation(
    *,
    container: AppContainer,
    current_user: User,
    media_kind: MediaKind,
    input_kind: InputKind,
    prompt: str,
    source_image_url: str | None,
    callback_url: str | None,
) -> GenerationResponse:
    try:
        generation = await container.generation_service.create_generation(
            user_id=current_user.id,
            media_kind=media_kind,
            input_kind=input_kind,
            prompt=prompt,
            source_image_url=source_image_url,
            callback_url=callback_url,
        )
    except Exception as exc:  # pragma: no cover - mapped centrally
        raise map_service_error(exc) from exc

    try:
        generation = await container.generation_service.mark_generation_queued(
            current_user.id,
            generation.id,
        )
        enqueue_generation(generation.id)
    except Exception as exc:
        await container.generation_service.mark_enqueue_failed(
            generation.id,
            f"failed to enqueue generation task: {exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="generation queue is unavailable",
        ) from exc

    return GenerationResponse.model_validate(generation)
