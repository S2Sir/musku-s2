# MUSKU 2.0 Web Server Dockerfile for RunxBuild / Cloud Run
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Install deps first for layer cache (supports both requirements-server.txt and requirements.txt)
COPY requirements-server.txt requirements.txt* ./
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements-server.txt ]; then pip install --no-cache-dir -r requirements-server.txt; \
    elif [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Copy app source (respects .dockerignore: no secrets/logs/cache)
COPY . .

EXPOSE 8000

# RunxBuild health check routes to $PORT/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health',timeout=4).read()" || exit 1

CMD ["python", "app.py"]
