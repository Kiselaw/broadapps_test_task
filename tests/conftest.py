from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    database_path = tmp_path / "test.db"
    return Settings(
        database_url=f"sqlite+aiosqlite:///{database_path}",
        create_schema_on_startup=True,
        provider_order="fal",
        test_fal=True,
        test_callback_delivery=True,
        test_callback_failures_before_success=4,
        webhook_retry_delay_seconds=0,
        payment_webhook_secret="test-secret",
        internal_healthcheck_secret="healthcheck-secret",
        metrics_secret="metrics-secret",
    )


@pytest.fixture(autouse=True)
def disable_celery_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.presentation.api.routes.generations.enqueue_generation",
        lambda generation_id: None,
    )


@pytest.fixture
async def app(settings: Settings):
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
