FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /service
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
# System deps + Python 3.11 via deadsnakes PPA
RUN apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Upgrade pip for python3.11
RUN python3.11 -m pip install --upgrade pip

# Python deps
COPY requirements.txt .
RUN python3.11 -m pip install --no-cache-dir -r requirements.txt

# Application code
COPY app/ app/

# Model weights are mounted as a volume, not baked into image
# This keeps the image small and models updatable without rebuild
VOLUME /service/models

EXPOSE 8001

# Single worker for GPU (model can't be shared across processes safely)
# Use --limit-concurrency to queue requests instead of OOM
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--limit-concurrency", "2"]
