# Backend image: the SuperKart sales forecasting API (Flask app served by gunicorn)
# Python 3.14 - the same version the model was trained with
FROM python:3.14-slim

# Print logs immediately (no output buffering) and do not write .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first: Docker caches this layer and reinstalls only when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the application code, the serialized model, and its training profile (for the extrapolation warnings)
COPY app.py superkart_model.joblib training_profile.json ./

# Run as an unprivileged user rather than root
RUN useradd --create-home appuser
USER appuser

EXPOSE 7860

# Docker marks the container "unhealthy" if the health endpoint stops answering
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/', timeout=4)"

# gunicorn, a production web server: 2 worker processes (the 2-core Codespace machine has 2 CPU cores),
# listening on port 7860 on all interfaces, with one access-log line per request
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:7860", "--timeout", "60", "--access-logfile", "-", "app:superkart_api"]
