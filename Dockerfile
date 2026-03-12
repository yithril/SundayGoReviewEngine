# ── Base ─────────────────────────────────────────────────────────────────────
# Official NVIDIA image: CUDA 12.1 + cuDNN 8 as proper system libraries.
# Ubuntu 20.04 — the OS KataGo v1.15.3 was compiled on; has libssl1.1 + libzip5.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    wget unzip python3 python3-pip \
    libssl1.1 libzip5 \
    && rm -rf /var/lib/apt/lists/*

# ── KataGo v1.15.3 ───────────────────────────────────────────────────────────
# Last release before AppImages were introduced (v1.16.0+).
# The Linux zip (~40 MB) is a plain binary + bundled cuDNN .so files.
# No AppImage, no squashfs, no FUSE — just unzip and point at it.
#
# The wrapper sets LD_LIBRARY_PATH to the extraction dir so the bundled
# libcudnn.so.8 is found, while still inheriting the system path so that
# libcuda.so.1 (injected by the RunPod NVIDIA runtime) is also visible.
RUN wget -q \
      "https://github.com/lightvector/KataGo/releases/download/v1.15.3/katago-v1.15.3-cuda12.1-cudnn8.9.7-linux-x64.zip" \
      -O /tmp/katago.zip \
  && unzip /tmp/katago.zip -d /opt/katago-bin \
  && KATAGO_BIN=$(find /opt/katago-bin -name "katago" -type f | head -1) \
  && KATAGO_DIR=$(dirname "$KATAGO_BIN") \
  && chmod +x "$KATAGO_BIN" \
  && printf '#!/bin/sh\nexec env LD_LIBRARY_PATH=%s${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} %s "$@"\n' \
       "$KATAGO_DIR:" "$KATAGO_BIN" > /usr/local/bin/katago \
  && chmod +x /usr/local/bin/katago \
  && rm /tmp/katago.zip \
  && echo "KataGo installed at: $KATAGO_BIN"

# ── KataGo model ─────────────────────────────────────────────────────────────
# b18 — 18 blocks, fast and strong. Good balance for game review latency.
# Filename matches what .env / .env.example specifies for KATAGO_MODEL.
RUN mkdir -p /opt/katago \
  && wget -q \
       "https://media.katagotraining.org/uploaded/networks/models/kata1/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz" \
       -O /opt/katago/kata1-b18c384nbt-s9996604416-d4316597426.bin.gz

# ── Python deps ──────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# ── App code ─────────────────────────────────────────────────────────────────
COPY katago/analysis.cfg /opt/katago/analysis.cfg
COPY handler.py          ./
COPY katago/             ./katago/
COPY sgf/                ./sgf/
COPY review/             ./review/
COPY storage/            ./storage/
COPY mailer/             ./mailer/

CMD ["python3", "handler.py"]
