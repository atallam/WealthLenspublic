# ╔══════════════════════════════════════════════════════════════╗
# ║  WealthLens OSS — Production Docker Build                  ║
# ║  Multi-stage: Node (frontend) → Python (backend + serve)   ║
# ╚══════════════════════════════════════════════════════════════╝

# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + serve built frontend
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app/ ./app/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Create non-root user
RUN useradd -m -r wealthlens && chown -R wealthlens:wealthlens /app
USER wealthlens

# Runtime
ENV PORT=8000
ENV ENVIRONMENT=production
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --timeout-keep-alive 120
