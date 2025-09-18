# Dockerfile - Lightweight non-music Discord bot
FROM python:3.12-slim

# environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# install minimal apt deps (kept small)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# set workdir
WORKDIR /app

# copy dependency list first to leverage cache
COPY requirements.txt /app/

# install python deps
RUN python3 -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# copy rest of project
COPY . /app

# create non-root user
RUN useradd --create-home --shell /bin/bash botuser || true
RUN chown -R botuser:botuser /app
USER botuser

# expose keep-alive port
EXPOSE 8080

# run the bot
CMD ["python3", "main.py"]