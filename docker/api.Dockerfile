# Python image for the API, the data pipeline and model training (same code, different command).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# geopandas / rasterio / pyproj ship manylinux wheels with GDAL+PROJ bundled; curl is for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY sentinel/ sentinel/
COPY configs/ configs/
COPY run_all.py ./

RUN useradd --create-home --uid 1000 sentinel && mkdir -p data/raw outputs logs models && chown -R sentinel /app
USER sentinel

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "sentinel.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
