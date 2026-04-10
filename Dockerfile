FROM python:3.13-slim

WORKDIR /app

# System dependencies for PyArrow & SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install uv/poetry or directly use pip with requirements mapped.
# Because the project uses pyproject.toml, we can install the package directly.
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# Using pip to handle local installation
RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir pytest

# Ensure our local physical fixtures for collect() are present
COPY tests/fixtures/ tests/fixtures/

# --- SMOKE TEST STEP ---
# Fails the Docker build immediately if tests regress! (Includes Auth, Registry, and Benchmarks)
# JWT_SECRET is mocked because the Fastapi app requires it at boot time to compile routes.
RUN JWT_SECRET="docker-build-time-secret-required-for-init-minimum-32" pytest tests -v

# Run the backend
EXPOSE 8000
CMD ["uvicorn", "src.agentic_poc.application.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
