# Dockerfile - Discord music bot (ffmpeg + PyNaCl support)
FROM python:3.12-slim

# Keep Python output unbuffered (helps logs) and avoid writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies: ffmpeg and build deps for PyNaCl/libsodium
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    pkg-config \
    libsodium-dev \
    libsndfile1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt /app/

# Install Python deps
RUN python3 -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . /app

# Create a non-root user for safety and drop permissions
RUN useradd --create-home --shell /bin/bash botuser || true
RUN chown -R botuser:botuser /app
USER botuser

# Expose port used by keep-alive web server (Flask)
EXPOSE 8080

# Healthcheck - optional (checks the keep-alive endpoint)
HEALTHCHECK --interval=1m --timeout=10s --start-period=10s \
  CMD wget -qO- http://127.0.0.1:8080/ || exit 1

# Run the bot
CMD ["python3", "main.py"]