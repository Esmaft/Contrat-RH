FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    ultralytics \
    fastapi \
    uvicorn \
    python-multipart \
    pdf2image

COPY signature_service.py .

RUN mkdir -p models

EXPOSE 8002

CMD ["uvicorn", "signature_service:app", "--host", "0.0.0.0", "--port", "8002"]