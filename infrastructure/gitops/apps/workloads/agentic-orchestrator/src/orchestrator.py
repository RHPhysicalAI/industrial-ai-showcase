# This project was developed with assistance from AI tools.
"""
Agentic Orchestrator - LangGraph-based read-only agent
Connects vLLM (brain) with MCP MLflow tools
"""
import os
import json
from typing import TypedDict, Annotated, Sequence
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import httpx


# Environment configuration
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm-agent-brain.agentic-ops.svc.cluster.local:8000/v1")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080")
MCP_FLEET_URL = os.getenv("MCP_FLEET_URL", "http://mcp-fleet-server.agentic-ops.svc.cluster.local:8080")
AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://audit-service.agentic-ops.svc.cluster.local:8090")


# MCP client for tool discovery and invocation
class MCPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)
        self._tool_schemas = {}  # Cache for tool schemas

    def discover_tools(self) -> list[dict]:
        """Discover available MCP tools"""
        response = self.client.get(f"{self.base_url}/mcp/tools")
        response.raise_for_status()
        tools = response.json()["tools"]

        # Cache tool schemas for HIL gate
        for tool in tools:
            self._tool_schemas[tool["name"]] = tool

        return tools

    def get_tool_schema(self, tool_name: str) -> dict:
        """Get cached tool schema (includes state_modifying field)"""
        if not self._tool_schemas:
            self.discover_tools()
        return self._tool_schemas.get(tool_name, {})

    def invoke_tool(self, tool_name: str, arguments: dict) -> dict:
        """Invoke an MCP tool - calls /tools/{tool_name} with GET or POST"""
        tool_schema = self.get_tool_schema(tool_name)

        # State-modifying tools use POST, read-only use GET
        if tool_schema.get("state_modifying", False):
            response = self.client.post(
                f"{self.base_url}/tools/{tool_name}",
                params=arguments
            )
        else:
            response = self.client.get(
                f"{self.base_url}/tools/{tool_name}",
                params=arguments
            )

        response.raise_for_status()
        return response.json()


# Initialize MCP client
mcp_client = MCPClient(MCP_BASE_URL)
mcp_fleet_client = MCPClient(MCP_FLEET_URL)  # Milestone 3: Fleet tools


# LangChain tool wrappers for MCP tools
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
def list_runs(experiment_id: str, max_results: int = 10) -> str:
    """List runs for a specific MLflow experiment"""
    result = mcp_client.invoke_tool("list_runs", {
        "experiment_id": experiment_id,
        "max_results": max_results
    })
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


def _register_model_impl(run_id: str, model_name: str) -> str:
    """Implementation of register_model - calls MCP"""
    result = mcp_client.invoke_tool("register_model", {
        "run_id": run_id,
        "model_name": model_name
    })
    return json.dumps(result, indent=2)


@tool
def register_model(run_id: str, model_name: str) -> str:
    """Register a model from a run (state-modifying action - requires approval)"""
    # This will be intercepted by custom_tool_node before execution
    return _register_model_impl(run_id, model_name)


# ========== FLEET TOOLS (Milestone 3) ==========

def _get_fleet_status_impl(factory: str = None) -> str:
    """Implementation of get_fleet_status - calls MCP Fleet"""
    result = mcp_fleet_client.invoke_tool("get_fleet_status", {"factory": factory} if factory else {})
    return json.dumps(result, indent=2)


@tool
def get_fleet_status(factory: str = None) -> str:
    """Get current fleet status across all factories or specific factory"""
    return _get_fleet_status_impl(factory)


def _get_factory_config_impl(factory: str) -> str:
    """Implementation of get_factory_config - calls MCP Fleet"""
    result = mcp_fleet_client.invoke_tool("get_factory_config", {"factory": factory})

    # Add a clear summary at the top so the model knows it has the answer
    policy_version = result.get("policy_version", "unknown")
    summary = f"The current model version deployed to {factory} is: {policy_version}\n\nFull configuration:\n"

    return summary + json.dumps(result, indent=2)


@tool
def get_factory_config(factory: str) -> str:
    """Get configuration for a specific factory including THE CURRENT MODEL VERSION (called policy_version)"""
    return _get_factory_config_impl(factory)


def _promote_policy_version_impl(factory: str, model_version: str) -> str:
    """Implementation of promote_policy_version - calls MCP Fleet (opens PR)"""
    result = mcp_fleet_client.invoke_tool("promote_policy_version", {
        "factory": factory,
        "model_version": model_version
    })
    return json.dumps(result, indent=2)


@tool
def promote_policy_version(factory: str, model_version: str) -> str:
    """Promote model policy version to factory (opens GitHub PR - requires approval)"""
    # This will be intercepted by custom_tool_node before execution
    return _promote_policy_version_impl(factory, model_version)


# Mark which tools are state-modifying
STATE_MODIFYING_TOOLS = {"register_model", "promote_policy_version"}


# LangGraph state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], "The messages in the conversation"]
    session_id: str  # Session ID for tracking approval requests
    pending_approval_id: int | None  # ID of pending approval request


# Initialize LLM (vLLM endpoint)
llm = ChatOpenAI(
    base_url=VLLM_BASE_URL,
    api_key="EMPTY",  # vLLM doesn't require API key
    model="meta-llama/Llama-3.1-8B-Instruct",
    temperature=0.7,
)

# Tool lists
read_only_tools = [
    list_experiments, get_experiment, list_runs, get_run, get_metrics,
    get_fleet_status, get_factory_config  # Milestone 3: Fleet read-only tools
]
state_modifying_tools_list = [
    register_model,
    promote_policy_version  # Milestone 3: Agent-opens-PR pattern
]
all_tools = read_only_tools + state_modifying_tools_list

# Bind ALL tools to LLM (so it knows about them)
llm_with_tools = llm.bind_tools(all_tools)

# But ToolNode only gets read-only tools
tools = all_tools  # Keep this for compatibility


# Agent node
def call_agent(state: AgentState) -> dict:
    """Agent decision node - decides whether to use tools or respond"""
    messages = state["messages"]
    print(f"DEBUG [call_agent]: Processing {len(messages)} messages")
    response = llm_with_tools.invoke(messages)

    # Debug tool calls
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print(f"DEBUG [call_agent]: Agent wants to call {len(response.tool_calls)} tools:")
        for tc in response.tool_calls:
            print(f"  - {tc.get('name')}({tc.get('args')})")
    else:
        print(f"DEBUG [call_agent]: Agent responding with text (no tools)")

    return {"messages": [response]}


# Custom tool node that checks for state-modifying tools
def custom_tool_node(state: AgentState) -> dict:
    """
    Custom tool execution node that intercepts state-modifying tools.
    If a state-modifying tool is called, create approval request instead of executing.
    """
    messages = state["messages"]
    last_message = messages[-1]

    # Check if this is an AIMessage with tool calls
    if not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
        return {"messages": []}

    # Process ALL tool calls (there may be multiple)
    result_messages = []

    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        tool_call_id = tool_call.get("id")

        # Check if state-modifying
        if tool_name in STATE_MODIFYING_TOOLS:
            # Create approval request instead of executing tool
            session_id = state.get("session_id", "unknown")

            # For promote_policy_version, pre-generate git_diff and summary
            git_diff = None
            summary = None
            if tool_name == "promote_policy_version":
                try:
                    # Call MCP Fleet to get git_diff and summary (but don't execute yet)
                    # We'll use the tool's implementation to get this data
                    import sys
                    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
                    from kustomize_generator import generate_promotion_git_diff, generate_promotion_summary

                    factory = tool_args.get("factory")
                    model_version = tool_args.get("model_version")
                    model_name = "vla-warehouse"  # Default model name
                    model_uri = f"s3://mlflow/models/{model_name}/{model_version}"

                    # Get factory namespace (K8s-compliant, e.g., "factory-b")
                    # factory might be display name with spaces (e.g., "Factory B")
                    # Call MCP Fleet directly to get the dict, not the LangChain tool wrapper
                    factory_config_result = mcp_fleet_client.invoke_tool("get_factory_config", {"factory": factory})
                    factory_namespace = factory_config_result.get("namespace", factory.lower().replace(" ", "-"))

                    git_diff = generate_promotion_git_diff(
                        model_name=model_name,
                        model_version=model_version,
                        model_uri=model_uri,
                        factory=factory_namespace,  # Use namespace for paths
                        namespace=factory_namespace
                    )
                    summary = generate_promotion_summary(
                        model_name=model_name,
                        model_version=model_version,
                        model_uri=model_uri,
                        factory=factory,  # Use display name for human-readable summary
                        namespace=factory_namespace
                    )
                except Exception as e:
                    print(f"Warning: Failed to generate git_diff/summary: {e}")

            audit_client = httpx.Client(timeout=30.0)
            try:
                audit_payload = {
                    "session_id": session_id,
                    "user_identity": "demo-operator",
                    "tool_name": tool_name,
                    "tool_arguments": tool_args
                }
                # Add git_diff and summary if available
                if git_diff:
                    audit_payload["git_diff"] = git_diff
                if summary:
                    audit_payload["summary"] = summary

                response = audit_client.post(
                    f"{AUDIT_SERVICE_URL}/audit/pending",
                    json=audit_payload
                )
                response.raise_for_status()
                approval_data = response.json()
                approval_id = approval_data["id"]

                # Store approval_id in state
                state["pending_approval_id"] = approval_id

                # Return a ToolMessage indicating approval needed
                tool_message = ToolMessage(
                    content=f"APPROVAL_REQUIRED: Request #{approval_id}",
                    tool_call_id=tool_call_id,
                    name=tool_name
                )

                result_messages.append(tool_message)
                print(f"HIL GATE: Created approval request #{approval_id} for {tool_name}")

            except Exception as e:
                print(f"Error creating approval request: {e}")
                # Fall through - will be executed by ToolNode below

        else:
            # Read-only tool - will be executed by ToolNode below
            pass

    # If we intercepted a state-modifying tool, return early with approval message
    if result_messages:
        # Return both messages AND pending_approval_id to update state
        return {
            "messages": result_messages,
            "pending_approval_id": state.get("pending_approval_id")
        }

    # Otherwise, execute read-only tools using default ToolNode
    # IMPORTANT: Only pass read_only_tools to avoid executing state-modifying tools
    from langgraph.prebuilt import ToolNode
    tool_executor = ToolNode(read_only_tools)
    return tool_executor.invoke(state)


# Conditional edge - should we continue or end?
def should_continue(state: AgentState) -> str:
    """Determine if we should continue to tools or end"""
    messages = state["messages"]
    last_message = messages[-1]

    # If there are tool calls, continue to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "continue"

    # Otherwise, end
    return "end"


# HIL Gate - check if last tool call needs approval
def check_hil_gate(state: AgentState) -> str:
    """
    After tool execution, check if approval is needed.
    The custom_tool_node marks state-modifying tools with APPROVAL_REQUIRED.
    """
    messages = state["messages"]
    last_message = messages[-1]

    # Check if last message is a ToolMessage with APPROVAL_REQUIRED marker
    if isinstance(last_message, ToolMessage):
        if last_message.content.startswith("APPROVAL_REQUIRED:"):
            # Approval request was created in custom_tool_node
            return "pending_approval"

    # Not requiring approval, continue to agent
    return "continue"


# Await approval node
def await_approval(state: AgentState) -> dict:
    """
    Node that handles pending approval state.
    Returns a message indicating approval is needed.
    """
    approval_id = state.get("pending_approval_id")

    # Add message to conversation
    waiting_message = AIMessage(
        content=f"⏸️  This action requires operator approval (Request #{approval_id}). Please review and approve/reject in the console."
    )

    return {"messages": [waiting_message]}


# Build the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", call_agent)
workflow.add_node("tools", custom_tool_node)  # Use custom tool node for HIL interception
workflow.add_node("await_approval", await_approval)

# Set entry point
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": END,
    }
)

# Add HIL gate after tools - check if approval needed
workflow.add_conditional_edges(
    "tools",
    check_hil_gate,
    {
        "continue": "agent",  # Read-only tools continue to agent
        "pending_approval": "await_approval",  # State-modifying tools wait for approval
    }
)

# Await approval ends the conversation (user must resume after approval)
workflow.add_edge("await_approval", END)

# Compile the graph
app = workflow.compile()


# Main agent interface
def run_agent(query: str, session_id: str = None) -> dict[str, any]:
    """
    Run the agent with a user query.

    Returns:
        dict with:
            - response: str - The agent's response message
            - pending_approval_id: int | None - ID if HIL approval was created
    """
    from langchain_core.messages import SystemMessage
    import uuid

    if session_id is None:
        session_id = f"session-{uuid.uuid4().hex[:8]}"

    system_prompt = """You are an AI assistant that helps operators manage ML models and factory operations.

CRITICAL: When you receive a tool result, RESPOND IMMEDIATELY. Do NOT call more tools.

FLEET QUESTIONS (policy version, robots, factory status):
- Use get_factory_config tool - it returns "policy_version" field which IS the model version
- Example: "What's the model version?" → call get_factory_config → respond with the policy_version value
- Do NOT call MLflow tools for factory/policy questions

MLFLOW QUESTIONS (experiments, runs, metrics):
- Use list_experiments, get_experiment, list_runs, get_run, get_metrics tools
- Only for questions about training experiments and metrics

WORKFLOW:
1. Read the question
2. Call ONE tool that answers it
3. When you get the tool result, STOP and respond - do NOT call another tool
4. Present the answer in natural language

STATE-MODIFYING ACTIONS (Require Approval):
- register_model - registers a new model in MLflow
- promote_policy_version - opens a GitHub PR to promote a model to a factory
"""

    initial_state = {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ],
        "session_id": session_id,
        "pending_approval_id": None
    }

    # Run the graph with recursion limit = 15 (agent → tools → agent = 3 steps per cycle)
    # Increased from 10 to handle fleet queries which might need 2-3 tool calls
    config = {"recursion_limit": 15}
    print(f"DEBUG [run_agent]: Starting query: {query[:100]}")
    try:
        final_state = app.invoke(initial_state, config=config)
        print(f"DEBUG [run_agent]: Completed successfully with {len(final_state['messages'])} messages")
    except Exception as e:
        # If we hit recursion limit, extract the last message before failing
        if "Recursion limit" in str(e):
            print(f"DEBUG [run_agent]: HIT RECURSION LIMIT after {len(initial_state['messages'])} steps")
            # Return a fallback response
            return "I apologize, but I encountered an issue processing your request. The system made too many tool calls. Please try rephrasing your question more specifically."
        raise

    # Extract final response and approval ID
    messages = final_state["messages"]
    last_message = messages[-1]
    pending_approval_id = final_state.get("pending_approval_id")

    response_text = last_message.content if isinstance(last_message, AIMessage) else str(last_message)

    return {
        "response": response_text,
        "pending_approval_id": pending_approval_id
    }


if __name__ == "__main__":
    # Test queries
    test_queries = [
        "What MLflow experiments are available?",
        "Show me details of experiment exp_001",
        "What are the metrics for run run_001_001?",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")
        response = run_agent(query)
        print(f"Response: {response}")