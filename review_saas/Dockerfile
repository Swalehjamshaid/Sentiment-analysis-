# ==========================================================
# filename: Dockerfile
# ENTERPRISE FASTAPI + PLAYWRIGHT + POSTGRESQL
# ==========================================================

# ==========================================================
# 1. BASE IMAGE
# ==========================================================

FROM python:3.12-slim

# ==========================================================
# 2. PYTHON ENVIRONMENT
# ==========================================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# ==========================================================
# 3. WORKING DIRECTORY
# ==========================================================

WORKDIR /app

# ==========================================================
# 4. SYSTEM DEPENDENCIES
# ==========================================================

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    wget \
    unzip \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
   
