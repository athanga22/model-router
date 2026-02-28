FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and migrations
COPY app/ ./app/
COPY migrations/ ./migrations/

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Cloud Run sets PORT env var — default to 8080
ENV PORT=8080

# Start the app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]