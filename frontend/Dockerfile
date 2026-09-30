FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
# Static files are served by the proxy container itself; no separate web server needed.
COPY --from=build /app/dist /srv
