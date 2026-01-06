# syntax=docker/dockerfile:1

# Using Alpine Linux for improved security and smaller image size
# Eliminates 4 High + 12 Medium + 11 Low vulnerabilities compared to slim
# Alpine reduces total vulnerabilities from 29 to 2 Low-severity issues
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-alpine as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for Python packages compilation
# Alpine uses apk package manager instead of apt-get
# These dependencies are commonly needed for Python packages with C extensions
RUN apk update && \
    apk add --no-cache \
        # GCC compiler for building Python packages with C extensions
        gcc \
        # musl C library development files (Alpine's libc implementation)
        musl-dev \
        # libffi development files for packages that use foreign function interface
        libffi-dev \
        # curl for health checks and debugging
        curl \
    # Clean up package cache to reduce image size
    && rm -rf /var/cache/apk/*

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Create directory for application and credentials with proper ownership
RUN mkdir -p /app/ && chown appuser:appuser /app/

# Copy service account credentials file
# This file is used for Google Cloud Platform authentication
COPY marketing-dwh-specs-100b60190539.json /app/marketing-dwh-specs-100b60190539.json
RUN chown appuser:appuser /app/marketing-dwh-specs-100b60190539.json

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# requirements.txt se copia explícitamente para que esté disponible durante el build en cualquier entorno.
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip && \
    python -m pip install -r /tmp/requirements.txt

# Switch to the non-privileged user to run the application.
# This improves security by not running the application as root.
USER appuser

# Copy the source code into the container.
# This is done after switching to appuser, so files will be owned by appuser.
COPY . .

# Expose the port that the application listens on.
EXPOSE 8000

# Configure health check to monitor application availability
# This allows Docker and orchestrators to know if the container is healthy
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/check || exit 1

# Run the application using uvicorn ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]