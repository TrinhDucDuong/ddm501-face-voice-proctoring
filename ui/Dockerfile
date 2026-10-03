FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /ui
COPY requirements-ui.txt .
RUN pip install -r requirements-ui.txt
COPY ui/app.py .
COPY ui/simulation.py ./ui/simulation.py
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /ui
USER appuser
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
