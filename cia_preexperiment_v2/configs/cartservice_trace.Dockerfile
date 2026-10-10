FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4
COPY --chown=1000:1000 . /app/
