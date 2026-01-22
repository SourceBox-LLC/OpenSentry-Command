# OpenSentry Command Center - Docker Image
# Uses official uv image for fast Python dependency management

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install system dependencies for OpenCV, Avahi, SSL, and video transcoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libavahi-client3 \
    avahi-daemon \
    dbus \
    openssl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Create directories for Avahi/D-Bus
RUN mkdir -p /var/run/dbus /var/run/avahi-daemon

# Expose Flask port
EXPOSE 5000

# Environment variables with defaults
ENV OPENSENTRY_USERNAME=admin
ENV OPENSENTRY_PASSWORD=opensentry
ENV FLASK_ENV=production

# Copy and set entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uv", "run", "run.py"]
