FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg2 \
    unzip \
    curl \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    fonts-liberation \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--timeout", "120", "--workers", "2", "app:app"]
