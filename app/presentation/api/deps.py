from fastapi import HTTPException, Request, status

from app.application.services import AuthenticationError
from app.core.container import AppContainer
from app.infrastructure.persistence.models import User


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def get_current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    return user


def map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    from app.application.services import BalanceError, NotFoundError

    if isinstance(exc, BalanceError):
        message = str(exc)
        status_code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if "rate limit" in message
            else status.HTTP_400_BAD_REQUEST
        )
        return HTTPException(status_code=status_code, detail=message)
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal server error"
    )
