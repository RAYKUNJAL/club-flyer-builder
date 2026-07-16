# Skin Blend IQ — single-container production image.
# Stage 1 builds the React frontend; stage 2 runs FastAPI and serves both
# the API and the built frontend on port 8000.

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./
# psycopg2 enables PostgreSQL via SBI_DATABASE_URL in production.
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary==2.9.10
COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend-dist

# /data holds the SQLite database and uploaded capture images by default.
# Point SBI_DATABASE_URL at PostgreSQL for multi-instance deployments.
ENV SBI_FRONTEND_DIST=/app/frontend-dist \
    SBI_DATABASE_URL=sqlite:////data/skin_blend_iq.db \
    SBI_UPLOAD_DIR=/data/uploads
VOLUME /data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
