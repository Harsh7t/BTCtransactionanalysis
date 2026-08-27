# One container. One port. One volume. Nothing to orchestrate.
#
# The UI is built in a first stage and copied in as static files, so the runtime
# image has no Node and the whole system is a single Python process serving both
# the API and the interface - no serialisation boundary, and no second service
# that can die during a demo.
FROM node:20-slim AS ui
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim
# libgomp is LightGBM's OpenMP runtime. Present here, so the container uses real
# LightGBM; on hosts without it (macOS without libomp) the detector falls back to
# scikit-learn's HistGradientBoosting and records which backend produced every
# number in the model manifest.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# VENDORED WHEELS ONLY. There is deliberately no `|| pip install .` fallback: a
# missing wheel must fail loudly here, on a machine with a network, rather than
# succeeding at build time and failing on the air-gapped one. Populate with
# `make wheels`.
COPY wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels \
      fastapi "uvicorn[standard]" pydantic python-multipart \
      numpy scipy scikit-learn polars pyarrow pandas \
      lightgbm shap duckdb python-igraph gensim \
      lxml ijson pyyaml jinja2 maxminddb \
      pytest hypothesis \
 && rm -rf /tmp/wheels

COPY btcfusion/ ./btcfusion/
COPY config/ ./config/
COPY data/geo/ ./data/geo/
COPY artifacts/ ./artifacts/
COPY tests/ ./tests/
COPY pyproject.toml README.md ./
COPY --from=ui /ui/dist ./ui/dist

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "btcfusion.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
