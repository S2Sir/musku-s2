# MUSKU 2.0 Web Server Dockerfile for Cloud Run Deployment
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy musku-2.0 application source code
COPY . /app

EXPOSE 8000

CMD ["python", "app.py"]
