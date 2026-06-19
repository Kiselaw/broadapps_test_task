FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/service/.venv
ENV PATH="/service/.venv/bin:$PATH"

WORKDIR /service

COPY pyproject.toml README.md alembic.ini /service/
COPY app /service/app
COPY migrations /service/migrations
COPY tests /service/tests

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
