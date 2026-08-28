# backend/Dockerfile - API Container
# Build context: backend/
# API listens on 0.0.0.0:8000

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Preserve the Python package directory so relative imports work.
COPY . /app/backend

EXPOSE 8000

# Healthcheck: verify API responds with status ok (includes real DB query)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request, json; r = urllib.request.urlopen('http://localhost:8000/health'); data = json.loads(r.read()); exit(0 if data.get('status') == 'ok' else 1)" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
