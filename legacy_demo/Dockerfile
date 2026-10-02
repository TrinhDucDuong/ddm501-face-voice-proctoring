FROM python:3.11-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2 requests==2.32.3 python-multipart==0.0.20
COPY legacy_demo /srv/legacy_demo
RUN useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser:appuser /data
USER appuser
CMD ["uvicorn", "legacy_demo.app:app", "--host", "0.0.0.0", "--port", "8000"]
