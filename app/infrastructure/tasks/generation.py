import asyncio
import logging

from app.core.config import get_settings
from app.core.container import AppContainer
from app.core.logging import configure_logging
from app.infrastructure.tasks.celery_app import celery_app
from app.infrastructure.tasks.webhooks import enqueue_webhook_delivery

logger = logging.getLogger(__name__)


@celery_app.task(name="generation-process", bind=True, max_retries=5)
def process_generation_task(self, generation_id: str) -> None:
    settings = get_settings()
    logger.info("processing generation task id=%s celery_id=%s", generation_id, self.request.id)
    delivery_id = asyncio.run(_process_generation(generation_id))
    if delivery_id:
        try:
            enqueue_webhook_delivery(delivery_id)
        except Exception as exc:
            raise self.retry(
                exc=exc,
                countdown=settings.webhook_retry_delay_seconds,
            ) from exc


def enqueue_generation(generation_id: str) -> None:
    settings = get_settings()
    process_generation_task.apply_async(
        args=[generation_id],
        queue=settings.celery_generation_queue,
        routing_key="generation-process",
        retry=True,
        retry_policy={
            "max_retries": 3,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 0.5,
        },
    )


async def _process_generation(generation_id: str) -> str | None:
    settings = get_settings()
    configure_logging(settings.log_dir)
    container = AppContainer(settings)
    await container.init()

    try:
        return await container.generation_worker_service.process_generation(generation_id)
    finally:
        await container.dispose()
