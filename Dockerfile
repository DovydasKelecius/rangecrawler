# Stage 1: Builder
FROM python:3.11-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    make

# Copy requirements and build wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Stage 2: Final Image
FROM python:3.11-alpine

WORKDIR /app

# Install and upgrade runtime dependencies for security patching
RUN apk add --no-cache openssh-client libffi openssl && \
    apk upgrade --no-cache

# Create a non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy built wheels from builder and install them
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy only necessary source files
COPY src/ /app/src/
COPY config.example.yaml /app/config.yaml

# Set ownership to appuser
RUN chown -R appuser:appgroup /app

# Environment variables
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

USER appuser

# Expose broker port (default)
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD nc -z localhost 8005 || exit 1

# Default command to run the broker
CMD ["python", "src/broker/main.py"]
