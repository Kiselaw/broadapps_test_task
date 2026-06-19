from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from app.application.services import AuthenticationError, BalanceError
from app.core.config import Settings, get_settings
from app.core.container import AppContainer
from app.core.logging import configure_logging
from app.core.metrics import api_requests_total
from app.presentation.api.routes import auth, generations, system, users, webhooks

logger = logging.getLogger(__name__)

EXCLUDED_AUTH_PATHS = {"/auth/register", "/webhooks/payments"}
INTERNAL_HEALTHCHECK_HEADER = "X-Internal-Healthcheck"
METRICS_HEADER = "X-Metrics-Secret"


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: AppContainer = app.state.container

    await container.init()

    try:
        yield
    finally:
        await container.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    configure_logging(app_settings.log_dir)

    app = FastAPI(
        title=app_settings.app_name,
        lifespan=app_lifespan,
    )

    app.state.container = AppContainer(app_settings)

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = (
                response.status_code if response else status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            api_requests_total.labels(
                path=request.url.path,
                method=request.method,
                status=str(status_code),
            ).inc()
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                status_code,
                elapsed_ms,
            )

    @app.middleware("http")
    async def auth_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in EXCLUDED_AUTH_PATHS:
            return await call_next(request)
        if (
            request.url.path == "/health"
            and request.headers.get(INTERNAL_HEALTHCHECK_HEADER)
            == app.state.container.settings.internal_healthcheck_secret
        ):
            return await call_next(request)
        if (
            request.url.path == "/metrics"
            and request.headers.get(METRICS_HEADER)
            == app.state.container.settings.metrics_secret
        ):
            return await call_next(request)
        if request.url.path in {"/health", "/metrics"}:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "invalid system credentials"},
            )

        api_key = request.headers.get(app.state.container.settings.api_key_header)
        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "missing API key"}
            )

        try:
            user = await app.state.container.auth_service.authenticate(api_key)
            await app.state.container.auth_service.enforce_rate_limit(user.id)
        except AuthenticationError as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)}
            )
        except BalanceError as exc:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": str(exc)}
            )

        request.state.user = user
        return await call_next(request)

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(generations.router)
    app.include_router(webhooks.router)

    return app


app = create_app()
