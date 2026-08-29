FROM node:22.23.2-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack prepare pnpm@11.20.0 --activate

WORKDIR /workspace
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

CMD ["./node_modules/.bin/vite", "--host", "0.0.0.0", "--port", "5173"]
