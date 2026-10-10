FROM python:3.13-slim
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://dl.k8s.io/release/v1.32.2/bin/linux/${TARGETARCH}/kubectl -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY obsplatform/ obsplatform/
COPY configs/mutations.json configs/mutations.json
COPY cia_preexperiment_v2/src/runtime/ cia_preexperiment_v2/src/runtime/
COPY cia_preexperiment_v2/src/method/oracle_probe.py cia_preexperiment_v2/src/method/oracle_probe.py
COPY cia_preexperiment_v2/data/mutations/method_controlled/ cia_preexperiment_v2/data/mutations/method_controlled/
COPY cia_preexperiment_v2/data/commits/method_replays/ cia_preexperiment_v2/data/commits/method_replays/
EXPOSE 8000
CMD ["uvicorn", "obsplatform.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
