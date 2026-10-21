FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY document_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY document_service/ /app
COPY shared/ /shared
COPY template_surat/ /template_surat

ENV PYTHONPATH=/shared

EXPOSE 8004
