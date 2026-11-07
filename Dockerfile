# Night Audit in two images from one file. A plain `docker build .` gives the demo.
#   demo  (default) the recorded demo nights of both apps, Vampires and Ghosts. No keys, no AWS account.
#         docker build -t night-audit . && docker run --rm -p 127.0.0.1:8000:8000 night-audit
#   app   tonight's audit of your own AWS account with your own read-only credentials, then the page for it.
#         See compose.yaml and .env.example.

FROM node:22.12.0-bookworm-slim AS web
WORKDIR /web
COPY skeleton/web/package.json skeleton/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY skeleton/web/ ./
RUN npm run build

FROM python:3.12.13-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_FROZEN=1 \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY skeleton/pyproject.toml skeleton/pyproject.toml
COPY apps/vampires/pyproject.toml apps/vampires/pyproject.toml
COPY apps/ghosts/pyproject.toml apps/ghosts/pyproject.toml
COPY apps/own-build/pyproject.toml apps/own-build/pyproject.toml
COPY skeleton/src skeleton/src
COPY apps apps
RUN uv sync --no-dev
COPY --from=web /web/dist skeleton/web/dist
RUN useradd --create-home --uid 10001 audit
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

FROM base AS app
# Credentials come from the environment (AWS_PROFILE with ~/.aws mounted read-only, or AWS_ACCESS_KEY_ID and friends)
# and should belong to a read-only role. Runs are kept in /data, a volume, so the night-over-night state survives.
RUN mkdir /data && chown audit /data
USER audit
VOLUME ["/data"]
CMD ["sh", "-c", "nightaudit run apps/vampires/controls/aws-account.yaml --runs /data/runs; exec nightaudit serve --app vampires --runs /data/runs --host 0.0.0.0 --port 8000"]

FROM base AS demo
# The three recorded Vampires nights are run here, offline, from the committed demo ledgers; the Ghosts nights are in
# the built front end already. Nothing reads AWS.
RUN python apps/vampires/demo/build.py && chown -R audit runs
USER audit
CMD ["nightaudit", "serve", "--app", "vampires", "--runs", "runs/demo", "--host", "0.0.0.0", "--port", "8000"]
