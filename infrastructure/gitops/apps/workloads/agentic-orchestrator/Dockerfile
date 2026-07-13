# This project was developed with assistance from AI tools.
FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better layer caching
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/src/ ./src/

# Create non-root user
RUN useradd -m -u 1001 -s /bin/bash agentuser && \
    chown -R agentuser:agentuser /app

USER agentuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health')"

# Run the API server
CMD ["python", "src/api_server.py"]