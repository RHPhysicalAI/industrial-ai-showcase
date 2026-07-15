# This project was developed with assistance from AI tools.
"""
Llama Stack Client for HIL Governance Integration

Wraps LangGraph agentic orchestrator with Llama Stack Agents API.
Per ADR-019: state-modifying tool calls route through HIL approval,
read-only tool calls pass through directly.

Architecture:
  User Query
      ↓
  LangGraph Agent (orchestrator.py)
      ↓
  Llama Stack Agents API (this module)
      ↓
  ┌─────────────┬──────────────┐
  │ Read-only   │ State-mod    │
  │ tools       │ tools        │
  │ (direct)    │ (HIL gate)   │
  └─────────────┴──────────────┘
"""
import os
import json
import httpx
from typing import Dict, List, Any, Optional
from datetime import datetime


# Environment configuration
LLAMA_STACK_URL = os.getenv(
    "LLAMA_STACK_URL",
    "http://llama-stack-hil-service.agentic-ops.svc.cluster.local:8321"
)


class LlamaStackClient:
    """
    Client for Llama Stack Agents API.

    Provides HIL governance layer around LangGraph agents per ADR-019.
    """

    def __init__(self, base_url: str = LLAMA_STACK_URL):
        self.base_url = base_url
        self.client = httpx.Client(timeout=60.0)

    def create_agent(
        self,
        agent_config: Dict[str, Any],
        instructions: str,
        enable_hil: bool = True
    ) -> str:
        """
        Create a Llama Stack agent.

        Args:
            agent_config: Agent configuration (model_id, tools, etc.)
            instructions: System instructions for the agent
            enable_hil: Whether to enable HIL approval for state-modifying tools

        Returns:
            agent_id: Unique identifier for the created agent
        """
        response = self.client.post(
            f"{self.base_url}/v1/agents/create",
            json={
                "agent_config": agent_config,
                "instructions": instructions,
                "enable_session_persistence": True,
                "enable_hil": enable_hil
            }
        )
        response.raise_for_status()
        return response.json()["agent_id"]

    def create_session(
        self,
        agent_id: str,
        session_name: str = None
    ) -> str:
        """
        Create a session for agent interaction.

        Args:
            agent_id: ID of the agent to create session for
            session_name: Optional name for the session

        Returns:
            session_id: Unique identifier for the session
        """
        response = self.client.post(
            f"{self.base_url}/v1/agents/session/create",
            json={
                "agent_id": agent_id,
                "session_name": session_name or f"session-{datetime.now().isoformat()}"
            }
        )
        response.raise_for_status()
        return response.json()["session_id"]

    def create_turn(
        self,
        agent_id: str,
        session_id: str,
        messages: List[Dict[str, Any]],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Create a turn in the agent conversation.

        This is where HIL approval happens. If the agent wants to call
        a state-modifying tool, the turn will pause and return pending_approval.

        Args:
            agent_id: ID of the agent
            session_id: ID of the session
            messages: List of messages (user messages, tool outputs, etc.)
            stream: Whether to stream the response

        Returns:
            turn_response: Contains agent's response or pending_approval
        """
        response = self.client.post(
            f"{self.base_url}/v1/agents/turn/create",
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                "messages": messages,
                "stream": stream
            }
        )
        response.raise_for_status()
        return response.json()

    def approve_tool_call(
        self,
        agent_id: str,
        session_id: str,
        turn_id: str,
        tool_call_id: str,
        approved: bool,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Approve or reject a pending tool call (HIL gate).

        Args:
            agent_id: ID of the agent
            session_id: ID of the session
            turn_id: ID of the turn with pending approval
            tool_call_id: ID of the specific tool call
            approved: True to approve, False to reject
            reason: Optional reason for approval/rejection

        Returns:
            approval_response: Result of approval decision
        """
        response = self.client.post(
            f"{self.base_url}/v1/agents/hil/approve",
            json={
                "agent_id": agent_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "tool_call_id": tool_call_id,
                "approved": approved,
                "reason": reason
            }
        )
        response.raise_for_status()
        return response.json()

    def get_session_history(
        self,
        agent_id: str,
        session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get full conversation history for a session.

        Args:
            agent_id: ID of the agent
            session_id: ID of the session

        Returns:
            messages: List of all messages in the session
        """
        response = self.client.get(
            f"{self.base_url}/v1/agents/session/get",
            params={
                "agent_id": agent_id,
                "session_id": session_id
            }
        )
        response.raise_for_status()
        return response.json().get("messages", [])

    def register_tools(
        self,
        tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Register MCP tools with Llama Stack.

        Args:
            tools: List of tool definitions (name, description, parameters, state_modifying flag)

        Returns:
            registration_result: Confirmation of tool registration
        """
        response = self.client.post(
            f"{self.base_url}/v1/tool-groups/register",
            json={
                "tool_group_id": "mcp-tools",
                "tools": tools,
                "provider_id": "meta-reference"  # Use meta-reference runtime for MCP tools
            }
        )
        response.raise_for_status()
        return response.json()

    def health_check(self) -> Dict[str, Any]:
        """
        Check if Llama Stack is healthy and reachable.

        Returns:
            health_status: Status information
        """
        response = self.client.get(f"{self.base_url}/v1/health")
        response.raise_for_status()
        return response.json()


# Singleton client instance
_llama_stack_client: Optional[LlamaStackClient] = None


def get_llama_stack_client() -> LlamaStackClient:
    """Get or create singleton Llama Stack client"""
    global _llama_stack_client
    if _llama_stack_client is None:
        _llama_stack_client = LlamaStackClient()
    return _llama_stack_client
