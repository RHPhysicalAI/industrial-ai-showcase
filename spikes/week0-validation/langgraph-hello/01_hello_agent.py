#!/usr/bin/env python3
"""
LangGraph Hello World - Simplest possible graph

This spike validates that LangGraph works with basic state management.
No LLM, no tools, just the graph execution pattern.

Usage:
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python 01_hello_agent.py

Expected output:
    Planning step...
    Executing step...
    Final result: {'messages': ['User asked a question', 'I am planning...'], 'result': 'Task complete!'}
"""
# This project was developed with assistance from AI tools.

from typing import TypedDict
from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    """Agent session state - persisted across graph nodes."""
    messages: list[str]
    result: str


def plan_step(state: AgentState) -> AgentState:
    """Planning node - adds a planning message."""
    print("Planning step...")
    state["messages"].append("I am planning...")
    return state


def execute_step(state: AgentState) -> AgentState:
    """Execution node - produces final result."""
    print("Executing step...")
    state["result"] = "Task complete!"
    return state


def main():
    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("plan", plan_step)
    workflow.add_node("execute", execute_step)

    # Define edges (flow)
    workflow.set_entry_point("plan")  # Start here
    workflow.add_edge("plan", "execute")  # plan -> execute
    workflow.add_edge("execute", END)  # execute -> end

    # Compile
    app = workflow.compile()

    # Run
    initial_state = {
        "messages": ["User asked a question"],
        "result": ""
    }

    final_state = app.invoke(initial_state)

    print(f"\nFinal result: {final_state}")


if __name__ == "__main__":
    main()