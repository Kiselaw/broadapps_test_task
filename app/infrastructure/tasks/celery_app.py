from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings

settings = get_settings()
exchange = Exchange("content_generation", type="direct", durable=True)

celery_app = Celery(
    "content_generation",
    broker=settings.celery_broker_url,
    include=[
        "app.infrastructure.tasks.generation",
        "app.infrastructure.tasks.webhooks",
    ],
)

celery_app.conf.update(
    enable_utc=True,
    task_acks_late=True,
    task_default_exchange=exchange.name,
    task_default_exchange_type=exchange.type,
    task_default_delivery_mode="persistent",
    task_default_queue=settings.celery_generation_queue,
    task_default_routing_key="generation-process",
    task_queues=(
        Queue(
            settings.celery_generation_queue,
            exchange=exchange,
            routing_key="generation-process",
            durable=True,
        ),
        Queue(
            settings.celery_webhooks_queue,
            exchange=exchange,
            routing_key="webhook-deliver",
            durable=True,
        ),
    ),
    task_reject_on_worker_lost=True,
    task_routes={
        "generation-process": {
            "queue": settings.celery_generation_queue,
            "routing_key": "generation-process",
        },
        "webhook-deliver": {
            "queue": settings.celery_webhooks_queue,
            "routing_key": "webhook-deliver",
        },
    },
    task_track_started=True,
    timezone="UTC",
    worker_prefetch_multiplier=1,
    broker_connection_timeout=3,
)
