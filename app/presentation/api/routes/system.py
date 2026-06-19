from fastapi import APIRouter, Response

from app.core.metrics import render_metrics

router = APIRouter(tags=["system"])


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)
