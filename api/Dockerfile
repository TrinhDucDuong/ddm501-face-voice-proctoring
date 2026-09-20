FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-api.txt requirements-models.txt ./
ARG INSTALL_PRETRAINED=true
RUN pip install -r requirements-api.txt \
    && if [ "$INSTALL_PRETRAINED" = "true" ]; then \
         pip install torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cpu \
         && pip install -r requirements-models.txt; \
       fi
COPY api/app ./app
COPY pipeline ./pipeline
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
