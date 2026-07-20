# Service Signature -- Detection YOLOv8 (GPU)
FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "numpy<2" "opencv-python-headless==4.11.0.86"
RUN pip install --no-cache-dir --no-deps ultralytics
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    pdf2image \
    matplotlib \
    pyyaml \
    requests \
    psutil \
    py-cpuinfo \
    "filelock>=3.16.1" \
    "numpy<2"
COPY signature_service.py .
EXPOSE 8002
CMD ["uvicorn", "signature_service:app", "--host", "0.0.0.0", "--port", "8002"]