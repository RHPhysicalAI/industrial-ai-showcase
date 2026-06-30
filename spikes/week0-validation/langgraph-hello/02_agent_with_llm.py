#!/usr/bin/env python3
"""
LangGraph + vLLM Integration Spike

This spike validates that LangGraph can call vLLM (via port-forward).

Prerequisites:
1. vLLM pod running (from ../vllm-test/)
2. Port-forward active: oc port-forward vllm-test 8000:8000 -n agentic-ops

Usage:
    source venv/bin/activate
    python 02_agent_with_llm.py

Expected output:
    Calling vLLM...
    Assistant: [coherent response about Paris]
"""
# This project was developed with assistance from AI tools.

from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage


def main():
    # Connect to vLLM (via port-forward)
    llm = ChatOpenAI(
        base_url="http://localhost:8000/v1",
        model="meta-llama/Llama-3.1-8B-Instruct",
        api_key="not-needed",  # vLLM doesn't require API key
        temperature=0.7,
        max_tokens=100,
    )

    # Test basic chat
    messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="What is the capital of France?"),
    ]

    print("Calling vLLM...")
    response = llm.invoke(messages)

    print(f"Assistant: {response.content}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Is vLLM pod running? oc get pod vllm-test -n agentic-ops")
        print("2. Is port-forward active? oc port-forward vllm-test 8000:8000 -n agentic-ops")
        print("3. Can you curl localhost:8000/health?")