FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Slim deps only — no scikit-learn/matplotlib/datasets; faster cold starts on Cloud Run
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

# Health check — uses httpx which is already a project dependency
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import httpx, os; httpx.get('http://localhost:' + os.getenv('PORT','8080') + '/v1/health', timeout=5).raise_for_status()"

# Start the app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]