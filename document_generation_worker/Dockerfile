FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        libreoffice-writer \
        fonts-dejavu \
        fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY document_generation_worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY document_generation_worker/ /app
COPY shared/ /shared
COPY template_surat/ /template_surat

ENV PYTHONPATH=/shared
