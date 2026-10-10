ARG BASE_IMAGE=us-central1-docker.pkg.dev/google-samples/microservices-demo/currencyservice:v0.10.4
FROM ${BASE_IMAGE}
COPY node_modules/ /usr/src/app/node_modules/
