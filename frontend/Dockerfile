# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build

ARG NPM_REGISTRY=https://registry.npmjs.org
ARG VITE_ICP_BEIAN_NUMBER

ENV VITE_ICP_BEIAN_NUMBER="$VITE_ICP_BEIAN_NUMBER"

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,id=onetree-frontend-npm,target=/root/.npm,sharing=locked \
    npm ci --registry="$NPM_REGISTRY" --prefer-offline --foreground-scripts \
    --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS dist

RUN mkdir -p /opt/onetree/frontend-dist/maintenance /opt/onetree/nginx/conf.d
COPY --from=build /app/dist/ /opt/onetree/frontend-dist/
COPY --from=build /app/node_modules/@fontsource/lxgw-wenkai/files/lxgw-wenkai-latin-500-normal.woff2 /opt/onetree/frontend-dist/maintenance/lxgw-wenkai-500-normal.woff2
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/conf.d/ /opt/onetree/nginx/conf.d/
COPY deploy/nginx/maintenance/index.html /opt/onetree/frontend-dist/maintenance/index.html

EXPOSE 80 443
