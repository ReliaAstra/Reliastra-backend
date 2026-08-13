# Dockerfile for Reliastra-backend
# Builds a production-ready image using Python 3.12

# Use the official Python 3.12 image as the base
FROM python:3.12-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the entire project directory
COPY . .

# Create a virtual environment and install dependencies
RUN python -m venv --copies /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --upgrade pip setuptools build && \
    pip install .

# Use the virtual environment in the final image
FROM python:3.12-slim

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Set environment variables for the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Set the working directory
WORKDIR /app

# Copy the application code
COPY . .

# Create required directories and set ownership
RUN mkdir -p /app/templates && chown -R appuser:appuser /app

# Expose the port the app runs on
EXPOSE 8000

# Switch to non-root user
USER appuser

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
