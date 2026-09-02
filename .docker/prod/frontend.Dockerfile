FROM node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS build

RUN corepack enable && corepack prepare pnpm@11.20.0 --activate
WORKDIR /workspace
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY web ./
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.29.5-alpine@sha256:42a7d7f2ee23e9f5a1dcdf3647ba5c585bbd18f79e79cd817e70e8cd61c55779
COPY --from=build /workspace/dist /usr/share/nginx/html
COPY .docker/prod/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=0755 .docker/prod/frontend-entrypoint.sh /usr/local/bin/ops-agent-nginx-entrypoint
EXPOSE 8443
