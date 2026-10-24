FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies: FFmpeg, Node.js, tini, HarfBuzz/Raqm Arabic text libs, and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    tini \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    fonts-noto-core \
    fonts-hosny-amiri \
    libraqm0 \
    libfribidi0 \
    libharfbuzz0b \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure jobs directory exists and configure non-root user
RUN mkdir -p /app/jobs && \
    useradd -m -u 10001 app && \
    chown -R app:app /app

USER app

EXPOSE 10000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
