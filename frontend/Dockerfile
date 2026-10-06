# =============================================================================
# Frontend image — build Angular, then serve the static output with nginx.
#
# Two stages so the ~300MB of node_modules never reaches the runtime image and
# the shipped artefact is exactly what `npm run build` produced.
# =============================================================================

# --- build --------------------------------------------------------------------
# Angular 22 requires Node ^20.19 || ^22.12 || >=24.
FROM node:24-alpine AS build

WORKDIR /app

# package-lock.json is copied so `npm ci` is reproducible. Copied before the rest
# of the source so editing a component does not re-run the install layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# angular.json's defaultConfiguration is "production", so this is the hashed,
# optimised build — no flag needed.
RUN npm run build

# --- runtime ------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Listens on 8080 rather than 80 so the published port is unprivileged.
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 8080

# `worker_processes auto` under a master that runs as root, workers as the nginx
# user — the stock posture for this image. Nothing in the container writes to
# disk, so there is no reason to relax it further.
CMD ["nginx", "-g", "daemon off;"]