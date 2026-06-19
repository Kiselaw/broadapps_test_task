import httpx

from app.core.config import Settings


class CallbackClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=settings.webhook_timeout_seconds)

    async def post_json(
        self,
        url: str,
        payload: dict,
        *,
        attempt_number: int,
    ) -> httpx.Response:
        if self.settings.test_callback_delivery:
            status_code = (
                500
                if attempt_number <= self.settings.test_callback_failures_before_success
                else 200
            )
            return httpx.Response(
                status_code=status_code,
                request=httpx.Request("POST", url),
                json={
                    "test_callback": True,
                    "attempt": attempt_number,
                    "payload": payload,
                },
            )

        return await self.client.post(url, json=payload)

    async def aclose(self) -> None:
        await self.client.aclose()
