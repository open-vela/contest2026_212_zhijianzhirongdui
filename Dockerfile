# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS web-builder
WORKDIR /build/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ARG APP_VERSION=0.2.0
ARG APP_UID=1000
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    STATIC_DIR=/app/server/static

WORKDIR /app/server
RUN groupadd --gid ${APP_UID} app && useradd --uid ${APP_UID} --gid app --create-home app
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
RUN rm -rf ./static && mkdir -p ./static ./data ./logs && chown -R app:app /app/server
COPY --from=web-builder --chown=app:app /build/client/dist/ ./static/

USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2))['status']=='ok'"

CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
