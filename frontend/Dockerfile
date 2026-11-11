# Frontend image: the SuperKart sales forecasting web app (Streamlit)
FROM python:3.14-slim

# Print logs immediately (no output buffering) and do not write .pyc files;
# BACKEND_URL: the backend container's name and port on the shared Docker network
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BACKEND_URL=http://backend:7860

WORKDIR /app

# Dependencies first: Docker caches this layer and reinstalls only when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the application code
COPY app.py .

# Run as an unprivileged user rather than root
RUN useradd --create-home appuser
USER appuser

EXPOSE 8501

# Docker marks the container "unhealthy" if Streamlit's own health endpoint stops answering
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

# Streamlit on port 8501, reachable from outside the container; no usage statistics sent; no watching for code
# changes (needed only during development). XSRF protection is disabled because Codespaces' port forwarding
# breaks Streamlit's XSRF cookie check, which would otherwise reject every file upload (HTTP 403)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false", "--server.fileWatcherType=none"]
