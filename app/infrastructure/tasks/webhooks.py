import asyncio
import logging

from app.application.services import RetryableWebhookDeliveryError
from app.core.config import get_settings
from app.core.container import AppContainer
from app.core.logging import configure_logging
from app.infrastructure.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="webhook-deliver", bind=True, max_retries=None)
def deliver_webhook_task(self, delivery_id: str) -> None:
    settings = get_settings()
    logger.info("delivering webhook id=%s celery_id=%s", delivery_id, self.request.id)

    try:
        asyncio.run(_deliver_webhook(delivery_id))
    except RetryableWebhookDeliveryError as exc:
        raise self.retry(
            exc=exc,
            countdown=settings.webhook_retry_delay_seconds,
        ) from exc


def enqueue_webhook_delivery(delivery_id: str) -> None:
    settings = get_settings()
    deliver_webhook_task.apply_async(
        args=[delivery_id],
        queue=settings.celery_webhooks_queue,
        routing_key="webhook-deliver",
        retry=True,
        retry_policy={
            "max_retries": 3,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 0.5,
        },
    )


async def _deliver_webhook(delivery_id: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_dir)
    container = AppContainer(settings)
    await container.init()

    try:
        await container.delivery_service.deliver_webhook(delivery_id)
    finally:
        await container.dispose()
