from fastapi import APIRouter, Depends

from app.core.container import AppContainer
from app.presentation.api.deps import get_container, map_service_error
from app.presentation.api.schemas import AuthRegisterRequest, AuthRegisterResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthRegisterResponse)
async def register_user(
    payload: AuthRegisterRequest,
    container: AppContainer = Depends(get_container),
) -> AuthRegisterResponse:
    try:
        user, api_key = await container.auth_service.register_user(
            external_user_id=str(payload.external_user_id),
            callback_url=str(payload.callback_url),
        )
    except Exception as exc:  # pragma: no cover - mapped centrally
        raise map_service_error(exc) from exc

    return AuthRegisterResponse(
        id=user.id,
        external_user_id=user.external_user_id,
        balance_tokens=user.balance_tokens,
        callback_url=user.callback_url,
        created_at=user.created_at,
        api_key=api_key,
    )
