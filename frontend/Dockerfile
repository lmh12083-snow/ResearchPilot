# ResearchPilot frontend — build the Vue app, serve the static bundle via nginx.
# Build context must be ./frontend (see root docker-compose.yml).
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first — layer stays cached unless lockfile changes.
# registry.npmjs.org is unreliable in CN — use the npmmirror registry.
COPY package.json package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
