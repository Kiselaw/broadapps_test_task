from app.application.services import (
    AuthService,
    DeliveryService,
    GenerationService,
    GenerationWorkerService,
    PaymentService,
    UserService,
)
from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory, init_database
from app.infrastructure.http import CallbackClient
from app.infrastructure.providers.router import ProviderRouter


class AppContainer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.engine = create_engine(self.settings.database_url)
        self.session_factory = create_session_factory(self.engine)
        self.callback_client = CallbackClient(self.settings)
        self.provider_router = ProviderRouter(self.settings, self.session_factory)

        self.auth_service = AuthService(self.session_factory, self.settings)
        self.user_service = UserService(self.session_factory)
        self.payment_service = PaymentService(self.session_factory)
        self.generation_service = GenerationService(self.session_factory, self.settings)
        self.generation_worker_service = GenerationWorkerService(
            self.session_factory,
            self.provider_router,
        )
        self.delivery_service = DeliveryService(
            self.session_factory,
            self.settings,
            self.callback_client,
        )

    async def init(self) -> None:
        if self.settings.create_schema_on_startup:
            await init_database(self.engine)

    async def dispose(self) -> None:
        await self.callback_client.aclose()
        await self.engine.dispose()
