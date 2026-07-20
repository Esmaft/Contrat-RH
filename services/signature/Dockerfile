# Service Signature -- Detection YOLOv8 (GPU)
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

WORKDIR /app

# Dependances systeme : poppler (conversion PDF->image), libgl (opencv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY signature_service.py .

EXPOSE 8002

CMD ["uvicorn", "signature_service:app", "--host", "0.0.0.0", "--port", "8002"]
