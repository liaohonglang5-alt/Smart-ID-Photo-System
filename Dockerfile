FROM python:3.10.12

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create uploads directory
RUN mkdir -p static/uploads

# Expose the port
EXPOSE 5001

# Run with gunicorn for better performance and larger request support
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--timeout", "300", "--workers", "2", "--max-request-size", "52428800", "app:app"]