# Python Build Stage
FROM python:3.11-slim-bookworm AS python-builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++

# Create a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies
COPY requirements.txt .
# Install CPU-only PyTorch first to prevent downloading huge NVIDIA/CUDA packages
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Pre-cache tiktoken encoding to avoid runtime download (VPC blocks network)
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache
RUN mkdir -p /opt/tiktoken_cache && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Final Production Image
FROM python:3.11-slim-bookworm
WORKDIR /app

# Create a non-root user
RUN useradd --create-home appuser
USER appuser

# Copy the virtual environment from the python-builder stage
COPY --from=python-builder /opt/venv /opt/venv

# Copy pre-cached tiktoken encoding from builder
COPY --from=python-builder /opt/tiktoken_cache /opt/tiktoken_cache
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache

# Copy the application source code
COPY src/ /app/src/
COPY zbin/ /app/zbin/
COPY alembic.ini /app/
COPY alembic/ /app/alembic/

# Set the PATH to include the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Set default environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV CELERY_BROKER_URL=redis://localhost:6379/0
ENV CELERY_RESULT_BACKEND=redis://localhost:6379/0
ENV REDIS_URL=redis://localhost:6379/0

# Expose port
EXPOSE $PORT

# Default command runs the FastAPI app
CMD ["uvicorn", "src.etherion_ai.app:app", "--host", "0.0.0.0", "--port", "8080"]