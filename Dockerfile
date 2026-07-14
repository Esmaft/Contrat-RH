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

COPY requirements.txt .

# Installer torch CPU d'abord (plus léger pour Docker)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Installer doctr ensuite
RUN pip install --no-cache-dir python-doctr

# Installer le reste
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images_pretraitees

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]