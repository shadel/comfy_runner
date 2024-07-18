FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

# export timezone - for python3.9-dev install
ENV TZ=Europe/London

# place timezone data /etc/timezone
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update 
RUN apt-get install python3 python3-pip -y
RUN apt-get install git git-lfs -y
# RUN apt-get install nvidia-cuda-toolkit -y

WORKDIR /app

# RUN apt-get update && apt-get install -y nginx nodejs npm gcc g++ make wget && \
#     rm -rf /var/lib/apt/lists/*

# RUN wget https://github.com/busyloop/envcat/releases/download/v1.1.0/envcat-1.1.0.linux-x86_64 \
#     && chmod +x envcat-1.1.0.linux-x86_64 \
#     && mv envcat-1.1.0.linux-x86_64 /usr/bin/envcat \
#     && ln -sf /usr/bin/envcat /usr/bin/envtpl

COPY requirements.txt /app/runner/requirements.txt
RUN pip install -r /app/runner/requirements.txt

COPY ./.git /app/runner/.git
COPY ./data /app/runner/data
COPY ./examples /app/runner/examples
COPY ./utils /app/runner/utils
COPY ./constants.py /app/runner/constants.py
COPY ./__init__.py /app/runner/__init__.py
COPY ./inf.py /app/runner/inf.py
COPY ./setup.py /app/runner/setup.py

RUN python3 -m runner.setup

COPY ./setup.py /app/runner/setup.py
CMD ["python3", "-m", "runner.main"]
