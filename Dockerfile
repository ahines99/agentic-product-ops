FROM ghcr.io/astral-sh/uv:0.12.18 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --locked --no-dev --no-editable
RUN useradd --create-home productops
USER productops
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "agentic_product_ops.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
