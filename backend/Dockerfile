FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY pipeline ./pipeline
COPY backend ./backend
RUN pip install --no-cache-dir ".[api]" \
    && useradd --system --uid 1000 app

ENV MUNICIPIO_YAML=/app/config/municipio.yaml \
    ANON_DIR=/app/data/anon \
    RAW_DIR=/app/data/raw

USER app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
