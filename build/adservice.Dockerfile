FROM alpine:3.21 AS agent
RUN wget -q -O /javaagent.jar https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.31.1/opentelemetry-javaagent.jar
RUN echo 'bbf83c151b6400709e2f225bdd07a04f839d9d13b8b93464241333fd25d3e3ba  /javaagent.jar' | sha256sum -c -
FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/adservice:v0.10.4
COPY --from=agent /javaagent.jar /otel/javaagent.jar
