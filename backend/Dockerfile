# Use Python 3.12 slim as the base image
FROM python:3.12-slim

# Set environment variables to optimize Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies (needed for compiling native extensions, e.g., numpy)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to the latest version
RUN pip install --upgrade pip

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code
COPY . /app/

# Run the Django app with Gunicorn
CMD ["gunicorn", "vota_backend.wsgi:application", "--bind", "0.0.0.0:8000"]
