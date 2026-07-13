#!/usr/bin/env python3
"""
LangGraph + vLLM Integration Spike (Simplified)

This spike validates that we can call vLLM directly without langchain-openai compatibility issues.

Prerequisites:
1. vLLM pod running with port-forward: oc port-forward vllm-test 8000:8000 -n agentic-ops

Usage:
    source .venv/bin/activate
    python 02_agent_with_llm_simple.py

Expected output:
    Assistant: The capital of France is Paris.
"""
# This project was developed with assistance from AI tools.

import requests
import json


def call_vllm(messages, max_tokens=100):
    """Call vLLM directly via HTTP."""
    response = requests.post(
        "http://localhost:8000/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json={
            "model": "meta-llama/Llama-3.1-8B-Instruct",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ]

    print("Calling vLLM...")
    answer = call_vllm(messages)

    print(f"Assistant: {answer}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Is vLLM pod running? oc get pod vllm-test -n agentic-ops")
        print("2. Is port-forward active? oc port-forward vllm-test 8000:8000 -n agentic-ops")
        print("3. Can you curl localhost:8000/health?")