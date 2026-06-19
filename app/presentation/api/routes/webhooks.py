from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.container import AppContainer
from app.presentation.api.deps import get_container, map_service_error
from app.presentation.api.schemas import BalanceResponse, PaymentWebhookRequest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/payments", response_model=BalanceResponse)
async def payment_webhook(
    payload: PaymentWebhookRequest,
    container: AppContainer = Depends(get_container),
    webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> BalanceResponse:
    if webhook_secret != container.settings.payment_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid webhook secret"
        )

    try:
        user = await container.payment_service.top_up(
            external_user_id=str(payload.external_user_id),
            amount=payload.amount,
            payload=payload.model_dump(mode="json"),
        )
    except Exception as exc:  # pragma: no cover - mapped centrally
        raise map_service_error(exc) from exc

    return BalanceResponse(
        user_id=user.id,
        balance_tokens=user.balance_tokens,
        reserved_tokens=user.reserved_tokens,
        available_tokens=user.available_tokens,
    )
