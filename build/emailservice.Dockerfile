FROM us-central1-docker.pkg.dev/google-samples/microservices-demo/emailservice:v0.10.4
COPY cia_preexperiment_v2/data/online-boutique/src/emailservice/email_server.py /email_server/email_server.py
