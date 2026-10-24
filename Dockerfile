FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies: FFmpeg, Node.js, OpenCV libs, and TrueType fonts (including Arabic fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    fonts-noto-core \
    fonts-hosny-amiri \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure jobs directory exists
RUN mkdir -p /app/jobs

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
