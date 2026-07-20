# Service OCR -- DocTR (GPU)
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    python-doctr \
    pdf2image \
    "numpy<2"
COPY ocr_service.py .
RUN mkdir -p /app/images_pretraitees
EXPOSE 8001
CMD ["uvicorn", "ocr_service:app", "--host", "0.0.0.0", "--port", "8001"]