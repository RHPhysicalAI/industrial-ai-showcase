# This project was developed with assistance from AI tools.
"""
Llama Stack Adapter for LangGraph Orchestrator

Bridges the existing LangGraph-based orchestrator with Llama Stack HIL governance.

Two integration modes:
1. PASSTHROUGH (default for now): Use existing HIL pattern in orchestrator.py
2. LLAMA_STACK: Route through Llama Stack Agents API for full governance

This adapter allows gradual migration from custom HIL to Llama Stack HIL.
"""
import os
import json
from typing import Dict, List, Any, Optional
from enum import Enum

from llama_stack_client import get_llama_stack_client


class HILMode(Enum):
    """HIL integration mode"""
    PASSTHROUGH = "passthrough"  # Use existing custom HIL in orchestrator.py
    LLAMA_STACK = "llama_stack"  # Use Llama Stack Agents API


# Configuration
HIL_MODE = HILMode(os.getenv("HIL_MODE", "passthrough"))


class LlamaStackAdapter:
    """
    Adapter that wraps LangGraph orchestrator with Llama Stack governance.

    In PASSTHROUGH mode: Acts as no-op, orchestrator uses existing HIL pattern
    In LLAMA_STACK mode: Routes through Llama Stack Agents API
    """

    def __init__(self, mode: HILMode = HIL_MODE):
        self.mode = mode
        self.client = get_llama_stack_client() if mode == HILMode.LLAMA_STACK else None
        self._agent_id: Optional[str] = None
        self._sessions: Dict[str, str] = {}  # session_id -> llama_stack_session_id

    def is_enabled(self) -> bool:
        """Check if Llama Stack mode is enabled"""
        return self.mode == HILMode.LLAMA_STACK

    def initialize_agent(
        self,
        tools: List[Dict[str, Any]],
        instructions: str = None
    ) -> Optional[str]:
        """
        Initialize Llama Stack agent with MCP tools.

        Args:
            tools: List of MCP tool definitions
            instructions: System instructions for agent

        Returns:
            agent_id if Llama Stack mode, None if passthrough
        """
        if not self.is_enabled():
            return None

        # Register MCP tools with Llama Stack
        self.client.register_tools(tools)

        # Create agent
        agent_config = {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "tool_groups": ["mcp-tools"],
            "enable_session_persistence": True
        }

        default_instructions = """
        You are an AI assistant for physical AI operations in an industrial warehouse.
        You have access to fleet management tools and MLflow model registry tools.

        When using tools:
        - Always check current state before making changes
        - Explain what you're about to do before executing state-modifying operations
        - For model promotions, verify the target factory and version before proceeding

        State-modifying operations (like promoting models) require human approval.
        """

        self._agent_id = self.client.create_agent(
            agent_config=agent_config,
            instructions=instructions or default_instructions,
            enable_hil=True
        )

        return self._agent_id

    def create_session(self, session_id: str) -> Optional[str]:
        """
        Create Llama Stack session for a LangGraph session.

        Args:
            session_id: LangGraph session ID

        Returns:
            llama_stack_session_id if Llama Stack mode, None if passthrough
        """
        if not self.is_enabled() or not self._agent_id:
            return None

        llama_session_id = self.client.create_session(
            agent_id=self._agent_id,
            session_name=f"langgraph-{session_id}"
        )

        self._sessions[session_id] = llama_session_id
        return llama_session_id

    def should_route_through_llama_stack(
        self,
        tool_name: str,
        is_state_modifying: bool
    ) -> bool:
        """
        Determine if this tool call should go through Llama Stack.

        Args:
            tool_name: Name of the tool being called
            is_state_modifying: Whether the tool modifies state

        Returns:
            True if should route through Llama Stack HIL
        """
        # In PASSTHROUGH mode, never route through Llama Stack
        if not self.is_enabled():
            return False

        # In LLAMA_STACK mode, route state-modifying tools
        # (read-only tools can still bypass for performance)
        return is_state_modifying

    def create_turn(
        self,
        session_id: str,
        user_message: str
    ) -> Dict[str, Any]:
        """
        Create a turn in Llama Stack agent conversation.

        Args:
            session_id: LangGraph session ID
            user_message: User's input message

        Returns:
            turn_response: Agent response or pending_approval
        """
        if not self.is_enabled():
            raise ValueError("create_turn called in passthrough mode")

        llama_session_id = self._sessions.get(session_id)
        if not llama_session_id:
            llama_session_id = self.create_session(session_id)

        return self.client.create_turn(
            agent_id=self._agent_id,
            session_id=llama_session_id,
            messages=[{
                "role": "user",
                "content": user_message
            }]
        )

    def approve_tool_call(
        self,
        session_id: str,
        turn_id: str,
        tool_call_id: str,
        approved: bool,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Approve or reject a pending tool call.

        Args:
            session_id: LangGraph session ID
            turn_id: Llama Stack turn ID
            tool_call_id: ID of the tool call
            approved: Approval decision
            reason: Optional reason

        Returns:
            approval_response
        """
        if not self.is_enabled():
            raise ValueError("approve_tool_call called in passthrough mode")

        llama_session_id = self._sessions.get(session_id)
        if not llama_session_id:
            raise ValueError(f"No Llama Stack session for {session_id}")

        return self.client.approve_tool_call(
            agent_id=self._agent_id,
            session_id=llama_session_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            approved=approved,
            reason=reason
        )

    def get_mode_description(self) -> str:
        """Get human-readable description of current mode"""
        if self.mode == HILMode.PASSTHROUGH:
            return "Passthrough (using custom HIL in orchestrator.py)"
        else:
            return "Llama Stack (using Llama Stack Agents API for HIL governance)"


# Singleton adapter instance
_adapter: Optional[LlamaStackAdapter] = None


def get_llama_stack_adapter() -> LlamaStackAdapter:
    """Get or create singleton Llama Stack adapter"""
    global _adapter
    if _adapter is None:
        _adapter = LlamaStackAdapter()
    return _adapter


def is_llama_stack_enabled() -> bool:
    """Quick check if Llama Stack mode is enabled"""
    return get_llama_stack_adapter().is_enabled()
