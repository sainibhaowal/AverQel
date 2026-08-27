FROM node:22-alpine AS builder

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN apk add --no-cache bash \
    && apk upgrade --no-cache
RUN corepack enable && corepack prepare pnpm@10.28.2 --activate

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml* .npmrc* ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG NEXT_PROXY_TARGET=http://api:1000
ARG GIT_VERSION=v1.0.0
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG DESKTOP_DOWNLOAD_BASE_URL=/downloads/latest
ENV NEXT_PROXY_TARGET=${NEXT_PROXY_TARGET}
ENV NEXT_PUBLIC_APP_VERSION=${GIT_VERSION}
ENV NEXT_PUBLIC_GIT_SHA=${GIT_SHA}
ENV NEXT_PUBLIC_BUILD_TIMESTAMP=${BUILD_TIMESTAMP}
ENV NEXT_PUBLIC_DESKTOP_DOWNLOAD_BASE_URL=${DESKTOP_DOWNLOAD_BASE_URL}
RUN pnpm build

FROM node:22-alpine AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=1030
WORKDIR /app

RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && addgroup -g 1001 -S nodejs \
    && adduser -S nextjs -u 1001 -G nodejs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 1030
CMD ["node", "server.js"]
