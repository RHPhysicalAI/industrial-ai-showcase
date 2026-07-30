# This project was developed with assistance from AI tools.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="MCP MLflow Server (Mock)" \
      org.opencontainers.image.description="Mock MCP server for MLflow tools - Phase 3 Milestone 1" \
      org.opencontainers.image.vendor="Red Hat Industrial AI Showcase" \
      org.opencontainers.image.version="0.1.0"

WORKDIR /app

# Install dependencies
COPY infrastructure/gitops/apps/workloads/mcp-mlflow-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY infrastructure/gitops/apps/workloads/mcp-mlflow-server/src/ ./src/

# Run as non-root user
RUN useradd -m -u 1001 mcpserver && \
    chown -R mcpserver:mcpserver /app

USER mcpserver

# Health check
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

EXPOSE 8080

CMD ["python", "-m", "src.mcp_server"]