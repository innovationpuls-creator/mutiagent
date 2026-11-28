# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22-alpine

FROM ${NODE_IMAGE} AS build
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /opt/onetree/ai-gateway
COPY ai-gateway/package.json ai-gateway/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm,sharing=locked \
    npm ci --registry="$NPM_REGISTRY" --prefer-offline --foreground-scripts
COPY ai-gateway/tsconfig.json ai-gateway/tsconfig.build.json ./
COPY ai-gateway/src ./src
RUN npm run build \
    && npm prune --omit=dev --registry="$NPM_REGISTRY"

FROM ${NODE_IMAGE} AS runtime
ENV NODE_ENV=production \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8100
WORKDIR /opt/onetree/ai-gateway
COPY --from=build --chown=node:node /opt/onetree/ai-gateway/package.json ./package.json
COPY --from=build --chown=node:node /opt/onetree/ai-gateway/node_modules ./node_modules
COPY --from=build --chown=node:node /opt/onetree/ai-gateway/dist ./dist
USER node
EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=12 \
    CMD node -e "fetch('http://127.0.0.1:8100/api/ai/health/live').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/server.js"]
