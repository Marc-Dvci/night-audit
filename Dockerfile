# Night Audit: run the skeleton, the Vampires app and the UI with no cloud credentials.
#   docker build -t night-audit .
#   docker run --rm -p 8000:8000 night-audit            # three demo nights, UI at http://localhost:8000/?demo=1
FROM node:22-slim AS web
WORKDIR /web
COPY skeleton/web/package.json skeleton/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY skeleton/web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY skeleton/pyproject.toml skeleton/pyproject.toml
COPY apps/vampires/pyproject.toml apps/vampires/pyproject.toml
COPY apps/ghosts/pyproject.toml apps/ghosts/pyproject.toml
COPY skeleton/src skeleton/src
COPY apps apps
RUN uv sync --frozen --no-dev
COPY scripts scripts
COPY casebook casebook
COPY --from=web /web/dist skeleton/web/dist
RUN uv run python apps/vampires/demo/build.py
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "nightaudit", "serve", "--app", "vampires", "--runs", "runs/demo", "--host", "0.0.0.0", "--port", "8000"]
