# This project was developed with assistance from AI tools.
FROM registry.access.redhat.com/ubi9/python-312:latest

USER root

WORKDIR /app

# Install system dependencies for OpenCV
RUN dnf install -y \
    mesa-libGL \
    glib2 \
    && dnf clean all

# Copy common library (build from repo root)
COPY workloads/common/python-lib /app/common-lib
RUN pip install --no-cache-dir -e /app/common-lib

# Copy application code (build from repo root)
COPY workloads/obstruction-detector-intel/src /app/src
COPY workloads/obstruction-detector-intel/pyproject.toml /app/

# Install application dependencies
RUN pip install --no-cache-dir -e .

USER 1001

# Run FastAPI with uvicorn
CMD ["uvicorn", "obstruction_detector_intel.main:app", "--host", "0.0.0.0", "--port", "8000"]