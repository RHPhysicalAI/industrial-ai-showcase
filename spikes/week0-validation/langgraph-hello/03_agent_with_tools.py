one one #!/usr/bin/env python3
"""
LangGraph + Tool Calling Spike

This spike validates that LangGraph can call tools (the pattern needed for MCP).

Prerequisites:
1. vLLM pod running with port-forward (same as 02_agent_with_llm.py)

Usage:
    source venv/bin/activate
    python 03_agent_with_tools.py

Expected output:
    Agent calling tool: get_temperature
    Tool returned: Temperature in Boston is 72°F
    Assistant: The temperature in Boston is 72°F
"""
# This project was developed with assistance from AI tools.

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent


@tool
def get_temperature(location: str) -> str:
    """Get the current temperature for a location.

    Args:
        location: The city name (e.g., "Boston", "New York")

    Returns:
        Temperature as a string
    """
    # Mock data - in real implementation, this would call mcp-mlflow or mcp-fleet
    temperatures = {
        "boston": "72°F",
        "new york": "68°F",
        "san francisco": "65°F",
    }

    temp = temperatures.get(location.lower(), "unknown")
    result = f"Temperature in {location} is {temp}"
    print(f"Tool returned: {result}")
    return result


@tool
def get_mlflow_metric(run_id: str, metric_name: str) -> str:
    """Get a metric from an MLflow run (mock implementation).

    Args:
        run_id: MLflow run ID (e.g., "v1.3", "v1.4")
        metric_name: Metric name (e.g., "pick_success_rate")

    Returns:
        Metric value as string
    """
    # Mock data - simulates mcp-mlflow response
    mock_data = {
        "v1.3": {"pick_success_rate": "0.76", "grasp_precision": "0.82"},
        "v1.4": {"pick_success_rate": "0.87", "grasp_precision": "0.91"},
    }

    run_data = mock_data.get(run_id, {})
    value = run_data.get(metric_name, "not found")
    result = f"Metric {metric_name} for run {run_id}: {value}"
    print(f"Tool returned: {result}")
    return result


def main():
    # Connect to vLLM
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        model="meta-llama/Llama-3.1-8B-Instruct",
        api_key="not-needed",
        temperature=0.7,
    )

    # Create tools list
    tools = [get_temperature, get_mlflow_metric]

    # Create ReAct agent (built-in LangGraph pattern)
    agent = create_react_agent(llm, tools)

    # Test 1: Simple tool call
    print("=" * 60)
    print("Test 1: Get temperature in Boston")
    print("=" * 60)

    result = agent.invoke({
        "messages": [("user", "What is the temperature in Boston?")]
    })

    print(f"\nAssistant: {result['messages'][-1].content}")

    # Test 2: MLflow-like tool call (simulates mcp-mlflow)
    print("\n" + "=" * 60)
    print("Test 2: Get MLflow metric")
    print("=" * 60)

    result = agent.invoke({
        "messages": [("user", "What is the pick success rate for model v1.4?")]
    })

    print(f"\nAssistant: {result['messages'][-1].content}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Is vLLM pod running? oc get pod vllm-test -n agentic-ops")
        print("2. Is port-forward active? oc port-forward vllm-test 8000:8000 -n agentic-ops")
        print("3. Does Llama 3.1 support tool calling? (Check vLLM logs for warnings)")