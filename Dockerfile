FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y nginx nodejs npm gcc g++ make wget && \
    rm -rf /var/lib/apt/lists/*

RUN wget https://github.com/busyloop/envcat/releases/download/v1.1.0/envcat-1.1.0.linux-x86_64 \
    && chmod +x envcat-1.1.0.linux-x86_64 \
    && mv envcat-1.1.0.linux-x86_64 /usr/bin/envcat \
    && ln -sf /usr/bin/envcat /usr/bin/envtpl

COPY requirements.txt /app/runner/requirements.txt
RUN pip install -r /app/runner/requirements.txt

COPY . /app/runner

CMD ["python", "-m", "runner.main"]
