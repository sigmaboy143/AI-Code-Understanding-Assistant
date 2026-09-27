FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create unprivileged non-root user (UID 10001)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g 10001 -m -s /bin/sh appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY --chown=appuser:appuser app ./app

# Run as unprivileged user
USER appuser

# Expose API port
EXPOSE 8000

# Start production server without reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
