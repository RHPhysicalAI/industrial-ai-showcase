#!/usr/bin/env python3
"""
MCP MLflow Server - Mock Implementation

This project was developed with assistance from AI tools.

Purpose: Mock MCP server exposing MLflow-like read-only tools for Milestone 1.

Tools:
- list_experiments: List all MLflow experiments
- get_experiment: Get details of a specific experiment
- list_runs: List runs for an experiment
- get_run: Get details of a specific run
- get_metrics: Get metrics for a run

This is a MOCK - returns fake data for testing the agent pattern.
Real MLflow integration happens in Milestone 2+.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uvicorn

app = FastAPI(
    title="MCP MLflow Server (Mock)",
    description="Mock MCP server for MLflow-like tools - Milestone 1",
    version="0.1.0"
)


# --- Mock Data ---

MOCK_EXPERIMENTS = [
    {
        "experiment_id": "exp-001",
        "name": "robot-navigation-training",
        "artifact_location": "s3://mlflow/exp-001",
        "lifecycle_stage": "active",
        "tags": {"team": "robotics", "project": "phase3"}
    },
    {
        "experiment_id": "exp-002",
        "name": "object-detection-vla",
        "artifact_location": "s3://mlflow/exp-002",
        "lifecycle_stage": "active",
        "tags": {"team": "perception", "project": "phase1"}
    },
    {
        "experiment_id": "exp-003",
        "name": "manipulation-policy",
        "artifact_location": "s3://mlflow/exp-003",
        "lifecycle_stage": "active",
        "tags": {"team": "manipulation", "project": "phase2"}
    }
]

MOCK_RUNS = {
    "exp-001": [
        {
            "run_id": "run-001-a",
            "experiment_id": "exp-001",
            "status": "FINISHED",
            "start_time": "2026-06-25T10:00:00Z",
            "end_time": "2026-06-25T14:30:00Z",
            "artifact_uri": "s3://mlflow/exp-001/run-001-a",
            "params": {
                "learning_rate": "0.001",
                "batch_size": "32",
                "epochs": "100"
            },
            "metrics": {
                "loss": 0.045,
                "accuracy": 0.956,
                "val_loss": 0.052,
                "val_accuracy": 0.948
            },
            "tags": {"model": "GR00T-N1.7", "gpu": "L40S"}
        },
        {
            "run_id": "run-001-b",
            "experiment_id": "exp-001",
            "status": "RUNNING",
            "start_time": "2026-07-01T08:00:00Z",
            "end_time": None,
            "artifact_uri": "s3://mlflow/exp-001/run-001-b",
            "params": {
                "learning_rate": "0.0005",
                "batch_size": "64",
                "epochs": "150"
            },
            "metrics": {
                "loss": 0.038,
                "accuracy": 0.962,
                "val_loss": 0.041,
                "val_accuracy": 0.959
            },
            "tags": {"model": "GR00T-N1.7", "gpu": "L40S"}
        }
    ],
    "exp-002": [
        {
            "run_id": "run-002-a",
            "experiment_id": "exp-002",
            "status": "FINISHED",
            "start_time": "2026-06-20T12:00:00Z",
            "end_time": "2026-06-20T18:45:00Z",
            "artifact_uri": "s3://mlflow/exp-002/run-002-a",
            "params": {
                "model": "yolov8",
                "confidence": "0.5",
                "iou_threshold": "0.45"
            },
            "metrics": {
                "mAP": 0.782,
                "precision": 0.845,
                "recall": 0.812
            },
            "tags": {"dataset": "warehouse-objects", "gpu": "L4"}
        }
    ]
}


# --- Pydantic Models ---

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class Experiment(BaseModel):
    experiment_id: str
    name: str
    artifact_location: str
    lifecycle_stage: str
    tags: Dict[str, str]


class Run(BaseModel):
    run_id: str
    experiment_id: str
    status: str
    start_time: str
    end_time: Optional[str]
    artifact_uri: str
    params: Dict[str, str]
    metrics: Dict[str, float]
    tags: Dict[str, str]


class MetricsResponse(BaseModel):
    run_id: str
    metrics: Dict[str, float]


# --- Health Check ---

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mcp-mlflow-server",
        "version": "0.1.0"
    }


# --- MCP Tools ---

@app.get("/tools/list_experiments", response_model=List[Experiment])
async def list_experiments():
    """
    List all MLflow experiments.

    Returns: List of experiments with metadata
    """
    return MOCK_EXPERIMENTS


@app.get("/tools/get_experiment", response_model=Experiment)
async def get_experiment(experiment_id: str):
    """
    Get details of a specific experiment.

    Args:
        experiment_id: ID of the experiment to retrieve

    Returns: Experiment details
    """
    for exp in MOCK_EXPERIMENTS:
        if exp["experiment_id"] == experiment_id:
            return exp

    raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")


@app.get("/tools/list_runs", response_model=List[Run])
async def list_runs(experiment_id: str):
    """
    List all runs for an experiment.

    Args:
        experiment_id: ID of the experiment

    Returns: List of runs with metrics and params
    """
    if experiment_id not in MOCK_RUNS:
        raise HTTPException(status_code=404, detail=f"No runs found for experiment {experiment_id}")

    return MOCK_RUNS[experiment_id]


@app.get("/tools/get_run", response_model=Run)
async def get_run(run_id: str):
    """
    Get details of a specific run.

    Args:
        run_id: ID of the run to retrieve

    Returns: Run details with metrics and params
    """
    # Search all experiments for the run
    for exp_id, runs in MOCK_RUNS.items():
        for run in runs:
            if run["run_id"] == run_id:
                return run

    raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


@app.get("/tools/get_metrics", response_model=MetricsResponse)
async def get_metrics(run_id: str):
    """
    Get metrics for a specific run.

    Args:
        run_id: ID of the run

    Returns: Metrics dictionary
    """
    # Search all experiments for the run
    for exp_id, runs in MOCK_RUNS.items():
        for run in runs:
            if run["run_id"] == run_id:
                return {
                    "run_id": run_id,
                    "metrics": run["metrics"]
                }

    raise HTTPException(status_code=404, detail=f"Run {run_id} not found")


# --- State-Modifying Tools (Milestone 2) ---

class RegisterModelRequest(BaseModel):
    run_id: str
    model_name: str


class RegisterModelResponse(BaseModel):
    model_name: str
    version: int
    run_id: str
    status: str
    message: str


@app.post("/tools/register_model", response_model=RegisterModelResponse)
async def register_model(run_id: str, model_name: str):
    """
    Register a model from a run (state-modifying).

    In mock implementation, this just returns success.
    In real MLflow, would call mlflow.register_model().

    Args:
        run_id: ID of the run to register model from
        model_name: Name for the registered model

    Returns: Model registration result
    """
    # Verify run exists
    run_found = False
    for exp_id, runs in MOCK_RUNS.items():
        for run in runs:
            if run["run_id"] == run_id:
                run_found = True
                break
        if run_found:
            break

    if not run_found:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Mock implementation - just return success
    return {
        "model_name": model_name,
        "version": 1,
        "run_id": run_id,
        "status": "registered",
        "message": f"Model '{model_name}' registered from run {run_id}"
    }


# --- MCP Discovery Endpoint ---

@app.get("/mcp/tools")
async def list_tools():
    """
    MCP tool discovery endpoint.
    Returns list of available tools for LangGraph agent.
    """
    return {
        "tools": [
            # Read-only tools
            {
                "name": "list_experiments",
                "description": "List all MLflow experiments",
                "state_modifying": False,
                "parameters": {},
                "endpoint": "/tools/list_experiments"
            },
            {
                "name": "get_experiment",
                "description": "Get details of a specific experiment",
                "state_modifying": False,
                "parameters": {
                    "experiment_id": {
                        "type": "string",
                        "description": "ID of the experiment",
                        "required": True
                    }
                },
                "endpoint": "/tools/get_experiment"
            },
            {
                "name": "list_runs",
                "description": "List all runs for an experiment",
                "state_modifying": False,
                "parameters": {
                    "experiment_id": {
                        "type": "string",
                        "description": "ID of the experiment",
                        "required": True
                    }
                },
                "endpoint": "/tools/list_runs"
            },
            {
                "name": "get_run",
                "description": "Get details of a specific run",
                "state_modifying": False,
                "parameters": {
                    "run_id": {
                        "type": "string",
                        "description": "ID of the run",
                        "required": True
                    }
                },
                "endpoint": "/tools/get_run"
            },
            {
                "name": "get_metrics",
                "description": "Get metrics for a specific run",
                "state_modifying": False,
                "parameters": {
                    "run_id": {
                        "type": "string",
                        "description": "ID of the run",
                        "required": True
                    }
                },
                "endpoint": "/tools/get_metrics"
            },
            # State-modifying tools (Milestone 2)
            {
                "name": "register_model",
                "description": "Register a model from a run (state-modifying action)",
                "state_modifying": True,
                "parameters": {
                    "run_id": {
                        "type": "string",
                        "description": "ID of the run to register model from",
                        "required": True
                    },
                    "model_name": {
                        "type": "string",
                        "description": "Name for the registered model",
                        "required": True
                    }
                },
                "endpoint": "/tools/register_model"
            }
        ]
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )