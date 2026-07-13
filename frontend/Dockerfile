# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build

ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --registry="$NPM_REGISTRY" --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine AS dist

RUN mkdir -p /opt/onetree/frontend-dist
COPY --from=build /app/dist/ /opt/onetree/frontend-dist/

EXPOSE 80 443
