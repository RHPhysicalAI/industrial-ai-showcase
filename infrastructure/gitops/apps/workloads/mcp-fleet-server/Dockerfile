# This project was developed with assistance from AI tools.
FROM registry.access.redhat.com/ubi9/python-311:latest

USER 0

WORKDIR /opt/app-root/src

# Copy requirements and install dependencies
COPY infrastructure/gitops/apps/workloads/mcp-fleet-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code (from repo root - Binary build context)
COPY infrastructure/gitops/apps/workloads/mcp-fleet-server/src/ ./src/

# Also copy shared code from agentic-orchestrator
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/src/github_client.py ./src/
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/src/kustomize_generator.py ./src/

# Set Python path
ENV PYTHONPATH=/opt/app-root/src

USER 1001

EXPOSE 8080

CMD ["python", "src/mcp_server.py"]
