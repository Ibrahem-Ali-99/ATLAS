FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
RUN addgroup -S atlas && adduser -S atlas -G atlas
COPY --from=build /app/public ./public
COPY --from=build --chown=atlas:atlas /app/.next/standalone ./
COPY --from=build --chown=atlas:atlas /app/.next/static ./.next/static
USER atlas
EXPOSE 3000
CMD ["node", "server.js"]
