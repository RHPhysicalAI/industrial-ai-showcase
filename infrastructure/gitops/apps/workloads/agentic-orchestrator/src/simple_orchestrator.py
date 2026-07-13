# This project was developed with assistance from AI tools.
"""
Simple Orchestrator - Direct tool calling without LangGraph loop
For Milestone 1 POC - validates vLLM + MCP integration
"""
import os
import json
import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool


# Environment configuration
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm-agent-brain.agentic-ops.svc.cluster.local:8000/v1")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080")


# MCP client
class MCPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)

    def invoke_tool(self, tool_name: str, arguments: dict) -> dict:
        """Invoke an MCP tool"""
        response = self.client.get(
            f"{self.base_url}/tools/{tool_name}",
            params=arguments
        )
        response.raise_for_status()
        return response.json()


mcp_client = MCPClient(MCP_BASE_URL)


# Define tools
@tool
def list_experiments() -> str:
    """List all MLflow experiments"""
    result = mcp_client.invoke_tool("list_experiments", {})
    return json.dumps(result, indent=2)


@tool
def get_experiment(experiment_id: str) -> str:
    """Get details of a specific MLflow experiment"""
    result = mcp_client.invoke_tool("get_experiment", {"experiment_id": experiment_id})
    return json.dumps(result, indent=2)


@tool
def list_runs(experiment_id: str) -> str:
    """List runs for a specific MLflow experiment"""
    result = mcp_client.invoke_tool("list_runs", {"experiment_id": experiment_id})
    return json.dumps(result, indent=2)


@tool
def get_run(run_id: str) -> str:
    """Get details of a specific MLflow run"""
    result = mcp_client.invoke_tool("get_run", {"run_id": run_id})
    return json.dumps(result, indent=2)


@tool
def get_metrics(run_id: str) -> str:
    """Get metrics for a specific MLflow run"""
    result = mcp_client.invoke_tool("get_metrics", {"run_id": run_id})
    return json.dumps(result, indent=2)


# LLM instance
llm = ChatOpenAI(
    base_url=VLLM_BASE_URL,
    api_key="EMPTY",
    model="meta-llama/Llama-3.1-8B-Instruct",
    temperature=0.7,
)

tools = [list_experiments, get_experiment, list_runs, get_run, get_metrics]
llm_with_tools = llm.bind_tools(tools)


def run_agent(query: str) -> str:
    """
    Simple 2-step agentic pattern:
    1. LLM decides which tool(s) to call
    2. LLM summarizes the results

    This avoids the infinite loop issue while still validating tool calling.
    """
    system_prompt = """You are an MLflow assistant that helps users query experiment tracking data.

When the user asks about experiments, runs, or metrics, call the appropriate tool to get the data,
then provide a clear, conversational summary of the results."""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]

    # Step 1: Get tool calls from LLM
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    # Step 2: Execute tools if any were called
    if hasattr(response, 'tool_calls') and response.tool_calls:
        # Execute each tool call
        for tool_call in response.tool_calls:
            tool_name = tool_call['name']
            tool_args = tool_call['args']

            # Find and execute the tool
            tool_func = next((t for t in tools if t.name == tool_name), None)
            if tool_func:
                try:
                    result = tool_func.invoke(tool_args)
                    messages.append(ToolMessage(
                        content=result,
                        tool_call_id=tool_call['id']
                    ))
                except Exception as e:
                    messages.append(ToolMessage(
                        content=f"Error calling {tool_name}: {str(e)}",
                        tool_call_id=tool_call['id']
                    ))

        # Step 3: Get final response with tool results
        final_response = llm.invoke(messages)
        return final_response.content

    # No tools called, return direct response
    return response.content


if __name__ == "__main__":
    # Test
    print(run_agent("What MLflow experiments are available?"))