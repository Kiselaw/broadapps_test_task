from fastapi import APIRouter, Depends

from app.infrastructure.persistence.models import User
from app.presentation.api.deps import get_current_user
from app.presentation.api.schemas import BalanceResponse, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/me/balance", response_model=BalanceResponse)
async def get_balance(current_user: User = Depends(get_current_user)) -> BalanceResponse:
    return BalanceResponse(
        user_id=current_user.id,
        balance_tokens=current_user.balance_tokens,
        reserved_tokens=current_user.reserved_tokens,
        available_tokens=current_user.available_tokens,
    )
