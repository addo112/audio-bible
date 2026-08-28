FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run with uvicorn on $PORT (default 10000 for Render / 8000 for local)
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"
