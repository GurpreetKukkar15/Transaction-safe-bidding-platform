FROM python:3.11.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY requirements ./requirements
COPY src ./src

RUN python -m pip install --no-cache-dir -r requirements/runtime.lock \
    && python -m pip install --no-cache-dir --no-deps . \
    && useradd --create-home --uid 10001 appuser

USER appuser

EXPOSE 8000

CMD ["uvicorn", "bidding.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
