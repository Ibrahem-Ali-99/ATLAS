FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Caddy publishes one origin and forwards /api itself. This rewrite is the
# fallback when a request reaches the Next.js process directly.
ARG ATLAS_API_URL=http://api:8000
ARG ATLAS_PUBLIC_SITE=1
ENV ATLAS_API_URL=$ATLAS_API_URL
ENV ATLAS_PUBLIC_SITE=$ATLAS_PUBLIC_SITE
ENV NEXT_STANDALONE=1
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
ENV ATLAS_PUBLIC_SITE=1
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S atlas && adduser -S atlas -G atlas
COPY --from=build /app/public ./public
COPY --from=build --chown=atlas:atlas /app/.next/standalone ./
COPY --from=build --chown=atlas:atlas /app/.next/static ./.next/static
USER atlas
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD node -e "fetch('http://127.0.0.1:3000/login').then((response)=>process.exit(response.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
