# Dockerfile for the VOTA backend, setting up a Python environment
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Command to run the Django server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]