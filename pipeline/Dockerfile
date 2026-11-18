FROM python:3.12-slim

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch torchvision ${TORCH_INDEX:+--index-url ${TORCH_INDEX}}

COPY pyproject.toml ./
RUN mkdir pipeline \
    && touch pipeline/__init__.py \
    && pip install --no-cache-dir ".[ml]" \
    && useradd --system --uid 1000 app

COPY pipeline ./pipeline

ENV HF_HOME=/hf

USER app
CMD ["python", "-m", "pipeline.worker"]
