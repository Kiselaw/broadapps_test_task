from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    app_name: str = "broadapps-content-service"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/broadapps"
    create_schema_on_startup: bool = False
    log_dir: str = "logs"

    api_key_header: str = "X-API-Key"
    payment_webhook_secret: str = "payment-secret"
    internal_healthcheck_secret: str = "healthcheck-secret"
    metrics_secret: str = "metrics-secret"

    request_rate_limit: int = 10
    request_rate_window_seconds: int = 60
    request_block_seconds: int = 60

    webhook_max_attempts: int = 5
    webhook_retry_delay_seconds: int = 15
    webhook_timeout_seconds: float = 10.0
    test_callback_delivery: bool = True
    test_callback_failures_before_success: int = 0

    celery_broker_url: str = "amqp://guest:guest@rabbitmq:5672//"
    celery_generation_queue: str = "generation"
    celery_webhooks_queue: str = "webhooks"
    celery_generation_concurrency: int = 2
    celery_webhook_concurrency: int = 4
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    provider_order: str = "fal,mock"

    test_fal: bool = True
    fal_api_key: str | None = None
    fal_text_to_image_model: str = "fal-ai/wan-25-preview/text-to-image"
    fal_image_to_image_model: str = "fal-ai/wan-25-preview/image-to-image"
    fal_text_to_video_model: str = "fal-ai/wan-25-preview/text-to-video"
    fal_image_to_video_model: str = "fal-ai/wan-25-preview/image-to-video"

    mock_provider_delay_seconds: float = 0.25
    mock_provider_base_url: str = "https://example.com/generated"
    test_fal_base_url: str = "https://example.com/fal-test"

    generation_prices: dict[str, int] = Field(
        default_factory=lambda: {
            "image:text": 10,
            "image:image": 15,
            "video:text": 40,
            "video:image": 50,
        }
    )

    @field_validator("fal_api_key", mode="before")
    @classmethod
    def empty_string_as_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @property
    def provider_chain(self) -> list[str]:
        return [item.strip() for item in self.provider_order.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
