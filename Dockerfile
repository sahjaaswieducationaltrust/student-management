# Multi-stage build: compile the React app, then fold it into the FastAPI image.
#
# This mirrors what .github/workflows/azure-deploy.yml does, but inside a single
# image so any Docker host (Render, Fly, Koyeb, a plain VM) can run the whole
# product from one container on one port. FastAPI serves the API under /api and
# the built SPA everywhere else — see backend/app/main.py.

# --------------------------------------------------------------------------- #
# Stage 1 — build the frontend
# --------------------------------------------------------------------------- #
FROM node:20-alpine AS frontend

WORKDIR /frontend

# Copy the manifests first so this layer stays cached until dependencies change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# No VITE_API_URL: the bundle makes same-origin relative /api calls, which is
# what we want when one container serves both halves.
RUN npm run build

# --------------------------------------------------------------------------- #
# Stage 2 — the runtime image
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

# PYTHONUNBUFFERED keeps logs streaming to the host's log viewer in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/tests ./tests

# main.py resolves STATIC_DIR as <parent of app/>/static -> /app/static.
COPY --from=frontend /frontend/dist ./static

# Run as a non-root user. Nothing is written to disk at runtime (receipts are
# generated in memory), so the app only needs read access to its own files.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Hosts inject the port to listen on via $PORT; 8000 is the local fallback.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
