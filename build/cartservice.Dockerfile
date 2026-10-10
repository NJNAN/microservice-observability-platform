FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src
COPY cia_preexperiment_v2/data/online-boutique/src/cartservice/src/ .
RUN dotnet publish -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -p:PublishTrimmed=false -o /out
FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4
COPY --from=build --chown=1000:1000 /out/ /app/
