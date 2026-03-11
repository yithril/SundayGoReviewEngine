# RunPod serverless worker — KataGo GPU analysis
# Requires NVIDIA GPU with CUDA 12.1+ (all standard RunPod GPU pods qualify)
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip wget unzip \
    && rm -rf /var/lib/apt/lists/*

# KataGo CUDA 12.1 binary
RUN wget -q "https://github.com/lightvector/KataGo/releases/download/v1.15.3/katago-v1.15.3-cuda12.1-cudnn8.9.7-linux-x64.zip" \
        -O /tmp/katago.zip \
    && unzip /tmp/katago.zip -d /tmp/katago_extracted \
    && find /tmp/katago_extracted -name "katago" -type f -exec mv {} /usr/local/bin/katago \; \
    && chmod +x /usr/local/bin/katago \
    && rm -rf /tmp/katago.zip /tmp/katago_extracted

# KataGo model (b18 — fast and strong, good for game review)
RUN mkdir -p /opt/katago && \
    wget -q "https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz" \
        -O /opt/katago/model.bin.gz

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY katago/analysis.cfg /opt/katago/analysis.cfg
COPY handler.py ./
COPY katago/  ./katago/
COPY sgf/     ./sgf/
COPY review/  ./review/
COPY storage/ ./storage/
COPY mailer/  ./mailer/

CMD ["python3", "handler.py"]
