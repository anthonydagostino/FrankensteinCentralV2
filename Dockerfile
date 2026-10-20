# Stage 1: build the SPA
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: python runtime
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 1000 frank
WORKDIR /app
COPY backend/pyproject.toml backend/README.md /app/backend/
COPY backend/app /app/backend/app
COPY backend/run.py /app/backend/run.py
RUN pip install --no-cache-dir /app/backend
COPY config /app/config
COPY --from=frontend /build/dist /app/static
RUN mkdir -p /app/data && chown -R frank:frank /app
USER frank
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
CMD ["python", "run.py"]
