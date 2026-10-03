FROM python:3.11-slim AS dependency-builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements-api.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements-api.txt

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsndfile1 curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dependency-builder /wheels /wheels
COPY requirements-models.txt ./
ARG INSTALL_PRETRAINED=true
RUN pip install /wheels/* && rm -rf /wheels \
    && if [ "$INSTALL_PRETRAINED" = "true" ]; then \
         pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cpu \
         && pip install -r requirements-models.txt; \
       fi
COPY api/app ./app
COPY pipeline ./pipeline
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /models /srv/data/simulation \
    && chown -R appuser:appuser /srv /models
USER appuser
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl --fail http://localhost:${PORT:-8000}/health || exit 1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
