# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build
#
# Runs the full dependency set, including devDependencies. @nestjs/cli (which
# provides `nest build`) and @types/jest (required by tsconfig.json's
# "types": ["node", "jest"]) are dev-only, so this stage cannot use
# --omit=dev.
# ---------------------------------------------------------------------------
FROM node:22-slim AS build

WORKDIR /app

# Copied before the source so this layer is only invalidated when the
# dependency manifest changes, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

# Build inputs only. tsconfig.build.json supplies rootDir ./src and excludes
# **/*spec.ts, so neither test/ nor the lint config is needed to compile.
COPY nest-cli.json tsconfig.json tsconfig.build.json ./
COPY src ./src
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — production runtime
#
# --omit=dev drops 555 dev-only lockfile entries. The resulting tree is pure
# JavaScript: the lockfile declares zero gypfile packages, and the only two
# packages with install scripts (@parcel/watcher, unrs-resolver) are
# dev-only, so nothing is compiled on the target platform.
# ---------------------------------------------------------------------------
FROM node:22-slim AS production

ENV NODE_ENV=production \
    PORT=3000

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Only compiled output is carried over. The build stage's devDependencies,
# TypeScript sources and tsbuildinfo never reach the runtime image.
COPY --from=build --chown=node:node /app/dist ./dist

# The stock node image ships an unprivileged `node` user (UID 1000).
USER node

EXPOSE 3000

# Liveness only. This probe deliberately hits /health and never /ready, so a
# missing or slow AI Engine cannot cause the runtime to be restarted: /health
# performs no network I/O. Readiness is the caller's concern, not the
# container's.
#
# node:22-slim ships neither curl nor wget, so this uses Node's built-in
# global fetch in exec form (no shell, so no variable expansion).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:' + (process.env.PORT || 3000) + '/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]

CMD ["npm", "run", "start:prod"]
