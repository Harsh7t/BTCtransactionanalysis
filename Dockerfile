# One container. One port. One volume. Nothing to orchestrate.
#
# The UI is built in a first stage and copied in as static files, so the runtime
# image has no Node and the whole system is a single Python process serving both
# the API and the interface — no serialisation boundary, and no second service
# that can die during a demo.
FROM node:20-slim AS ui
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim
# libgomp is LightGBM's OpenMP runtime. Present here, so the container uses real
# LightGBM; on hosts without it the detector falls back to scikit-learn's
# HistGradientBoosting and records which backend produced every number.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY btcfusion/ ./btcfusion/
COPY config/ ./config/
COPY data/geo/ ./data/geo/
COPY artifacts/ ./artifacts/
COPY --from=ui /ui/dist ./ui/dist

# Vendored wheels make the image buildable with networking disabled. Populate
# with:  uv pip download -r requirements.txt -d wheels/
COPY wheels* /tmp/wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels . \
    || pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "btcfusion.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
