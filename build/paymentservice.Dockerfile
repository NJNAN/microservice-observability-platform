FROM node:20-alpine AS deps
WORKDIR /deps
COPY configs/node-otel/package*.json ./
RUN npm ci --omit=dev --fetch-retries=3
FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/paymentservice:v0.10.4
COPY --from=deps /deps/node_modules/ /usr/src/app/node_modules/
COPY cia_preexperiment_v2/data/online-boutique/src/paymentservice/index.js /usr/src/app/index.js
