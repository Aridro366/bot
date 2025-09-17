# Use official Python image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install system dependencies (FFmpeg) and Python packages
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    pip install --no-cache-dir -r requirements.txt

# Copy all bot files into container
COPY . .

# Run the bot
CMD ["python", "bot.py"]