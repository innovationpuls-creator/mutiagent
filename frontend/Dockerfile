# ── 构建阶段 ──
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ── 运行阶段 ──
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx 配置由 docker-compose 挂载
EXPOSE 80
