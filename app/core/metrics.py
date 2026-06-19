from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

api_requests_total = Counter(
    "api_requests_total",
    "Total amount of API requests.",
    ["path", "method", "status"],
)
generation_total = Counter(
    "generation_total",
    "Generation tasks observed by media type and status.",
    ["media_kind", "input_kind", "status"],
)
generation_success_total = Counter(
    "generation_success_total",
    "Successful generation tasks.",
    ["provider", "media_kind", "input_kind"],
)
generation_error_total = Counter(
    "generation_error_total",
    "Failed generation tasks.",
    ["provider", "media_kind", "input_kind"],
)
generation_tokens_spent_total = Counter(
    "generation_tokens_spent_total",
    "Conditional tokens spent on successful generation tasks.",
    ["provider", "media_kind", "input_kind"],
)
webhook_delivery_total = Counter(
    "webhook_delivery_total",
    "Webhook delivery attempts.",
    ["status"],
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
