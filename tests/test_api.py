from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.domain.enums import DeliveryStatus, GenerationStatus
from app.infrastructure.persistence.models import WebhookDelivery


async def register_and_top_up(
    client: httpx.AsyncClient,
    external_user_id: str | None = None,
) -> dict:
    external_user_id = external_user_id or str(uuid4())
    register_response = await client.post(
        "/auth/register",
        json={
            "external_user_id": external_user_id,
            "callback_url": "https://client.example/webhook",
        },
    )
    assert register_response.status_code == 200
    payload = register_response.json()

    payment_response = await client.post(
        "/webhooks/payments",
        headers={"X-Webhook-Secret": "test-secret"},
        json={"external_user_id": payload["external_user_id"], "amount": 100},
    )
    assert payment_response.status_code == 200
    payload["balance"] = payment_response.json()["balance_tokens"]
    return payload

GENERATION_CASES = [
    (
        "/generations/images/text-to-image",
        {"prompt": "A lighthouse in fog"},
        "image",
        "text",
        10,
        {"prompt": "A lighthouse in fog"},
    ),
    (
        "/generations/images/image-to-image",
        {
            "prompt": "Make it cinematic",
            "source_image_url": "https://example.com/source.png",
        },
        "image",
        "image",
        15,
        {
            "prompt": "Make it cinematic",
            "image_urls": ["https://example.com/source.png"],
        },
    ),
    (
        "/generations/videos/text-to-video",
        {"prompt": "A slow dolly shot through fog"},
        "video",
        "text",
        40,
        {"prompt": "A slow dolly shot through fog"},
    ),
    (
        "/generations/videos/image-to-video",
        {
            "prompt": "Slow cinematic zoom",
            "source_image_url": "https://example.com/source.png",
        },
        "video",
        "image",
        50,
        {
            "prompt": "Slow cinematic zoom",
            "image_url": "https://example.com/source.png",
        },
    ),
]


async def create_and_process_generation(
    app,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    endpoint: str,
    payload: dict,
) -> dict:
    create_response = await client.post(endpoint, headers=headers, json=payload)
    assert create_response.status_code == 200
    created_generation = create_response.json()
    assert created_generation["status"] == GenerationStatus.QUEUED.value

    await app.state.container.generation_worker_service.process_generation(
        created_generation["id"]
    )

    fetch_response = await client.get(f"/generations/{created_generation['id']}", headers=headers)
    assert fetch_response.status_code == 200
    return fetch_response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "payload", "media_kind", "input_kind", "price", "fal_input"),
    GENERATION_CASES,
)
async def test_all_generation_types_complete(
    app,
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict,
    media_kind: str,
    input_kind: str,
    price: int,
    fal_input: dict,
) -> None:
    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    generation = await create_and_process_generation(app, client, headers, endpoint, payload)

    assert generation["status"] == GenerationStatus.COMPLETED.value
    assert generation["media_kind"] == media_kind
    assert generation["input_kind"] == input_kind
    assert generation["result_url"]
    assert generation["result_payload"]["input"] == fal_input

    balance_response = await client.get("/users/me/balance", headers=headers)
    assert balance_response.status_code == 200
    assert balance_response.json()["balance_tokens"] == 100 - price
    assert balance_response.json()["reserved_tokens"] == 0
    assert balance_response.json()["available_tokens"] == 100 - price


@pytest.mark.asyncio
async def test_full_generation_flow(app, client: httpx.AsyncClient) -> None:
    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    create_response = await client.post(
        "/generations/images/text-to-image",
        headers=headers,
        json={"prompt": "A lighthouse in fog"},
    )
    assert create_response.status_code == 200
    created_generation = create_response.json()
    assert created_generation["status"] == GenerationStatus.QUEUED.value

    reserved_balance_response = await client.get("/users/me/balance", headers=headers)
    assert reserved_balance_response.status_code == 200
    assert reserved_balance_response.json()["balance_tokens"] == 100
    assert reserved_balance_response.json()["reserved_tokens"] == 10
    assert reserved_balance_response.json()["available_tokens"] == 90

    await app.state.container.generation_worker_service.process_generation(created_generation["id"])

    fetch_response = await client.get(f"/generations/{created_generation['id']}", headers=headers)
    assert fetch_response.status_code == 200
    fetched_generation = fetch_response.json()
    assert fetched_generation["status"] == GenerationStatus.COMPLETED.value
    assert fetched_generation["result_url"]

    balance_response = await client.get("/users/me/balance", headers=headers)
    assert balance_response.status_code == 200
    assert balance_response.json()["balance_tokens"] == 90
    assert balance_response.json()["reserved_tokens"] == 0
    assert balance_response.json()["available_tokens"] == 90

    metrics_response = await client.get(
        "/metrics",
        headers={"X-Metrics-Secret": "metrics-secret"},
    )
    assert metrics_response.status_code == 200
    assert "generation_tokens_spent_total" in metrics_response.text
    assert "generation_cost_usd_total" not in metrics_response.text


@pytest.mark.asyncio
async def test_users_can_only_read_own_generations(
    app,
    client: httpx.AsyncClient,
) -> None:
    first_user = await register_and_top_up(client)
    second_user = await register_and_top_up(client)
    first_headers = {"X-API-Key": first_user["api_key"]}
    second_headers = {"X-API-Key": second_user["api_key"]}

    create_response = await client.post(
        "/generations/images/text-to-image",
        headers=first_headers,
        json={"prompt": "Private user generation"},
    )
    assert create_response.status_code == 200
    generation_id = create_response.json()["id"]

    await app.state.container.generation_worker_service.process_generation(generation_id)

    own_response = await client.get(f"/generations/{generation_id}", headers=first_headers)
    assert own_response.status_code == 200

    foreign_response = await client.get(f"/generations/{generation_id}", headers=second_headers)
    assert foreign_response.status_code == 404

    foreign_list_response = await client.get("/generations", headers=second_headers)
    assert foreign_list_response.status_code == 200
    assert all(item["id"] != generation_id for item in foreign_list_response.json())


@pytest.mark.asyncio
async def test_system_routes_require_authentication(client: httpx.AsyncClient) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 401

    metrics_response = await client.get("/metrics")
    assert metrics_response.status_code == 401

    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    authenticated_health_response = await client.get("/health", headers=headers)
    assert authenticated_health_response.status_code == 401

    authenticated_metrics_response = await client.get("/metrics", headers=headers)
    assert authenticated_metrics_response.status_code == 401

    internal_health_response = await client.get(
        "/health",
        headers={"X-Internal-Healthcheck": "healthcheck-secret"},
    )
    assert internal_health_response.status_code == 200

    internal_metrics_response = await client.get(
        "/metrics",
        headers={"X-Metrics-Secret": "metrics-secret"},
    )
    assert internal_metrics_response.status_code == 200


@pytest.mark.asyncio
async def test_generation_failure_releases_reserved_balance(app, client: httpx.AsyncClient) -> None:
    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    create_response = await client.post(
        "/generations/videos/text-to-video",
        headers=headers,
        json={"prompt": "force-fail video generation"},
    )
    assert create_response.status_code == 200
    generation_id = create_response.json()["id"]

    reserved_balance_response = await client.get("/users/me/balance", headers=headers)
    assert reserved_balance_response.status_code == 200
    assert reserved_balance_response.json()["balance_tokens"] == 100
    assert reserved_balance_response.json()["reserved_tokens"] == 40
    assert reserved_balance_response.json()["available_tokens"] == 60

    await app.state.container.generation_worker_service.process_generation(generation_id)

    fetch_response = await client.get(f"/generations/{generation_id}", headers=headers)
    assert fetch_response.status_code == 200
    assert fetch_response.json()["status"] == GenerationStatus.FAILED.value

    balance_response = await client.get("/users/me/balance", headers=headers)
    assert balance_response.status_code == 200
    assert balance_response.json()["balance_tokens"] == 100
    assert balance_response.json()["reserved_tokens"] == 0
    assert balance_response.json()["available_tokens"] == 100


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_ten_requests(client: httpx.AsyncClient) -> None:
    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    for _ in range(9):
        response = await client.get("/users/me", headers=headers)
        assert response.status_code == 200

    tenth_response = await client.get("/users/me", headers=headers)
    assert tenth_response.status_code == 200

    blocked_response = await client.get("/users/me", headers=headers)
    assert blocked_response.status_code == 429

    repeated_response = await client.get("/users/me", headers=headers)
    assert repeated_response.status_code == 429


@pytest.mark.asyncio
async def test_webhook_delivery_retries_until_success(app, client: httpx.AsyncClient) -> None:
    registration = await register_and_top_up(client)
    headers = {"X-API-Key": registration["api_key"]}

    create_response = await client.post(
        "/generations/images/text-to-image",
        headers=headers,
        json={"prompt": "A moonlit forest", "callback_url": "https://client.example/webhook"},
    )
    assert create_response.status_code == 200
    generation_id = create_response.json()["id"]

    await app.state.container.generation_worker_service.process_generation(generation_id)

    async with app.state.container.session_factory() as session:
        delivery = await session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.generation_id == generation_id)
        )

    assert delivery is not None

    for _ in range(5):
        try:
            await app.state.container.delivery_service.deliver_webhook(delivery.id)
        except Exception:
            pass

    async with app.state.container.session_factory() as session:
        row = await session.scalar(
            select(WebhookDelivery).where(WebhookDelivery.generation_id == generation_id)
        )

    assert row is not None
    assert row.status == DeliveryStatus.DELIVERED
    assert row.attempts == 5
