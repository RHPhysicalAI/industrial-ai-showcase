# This project was developed with assistance from AI tools.
"""
Tool Call Tracer - Captures agent's MCP tool execution history

Purpose: Track read-only tool calls to show operator the agent's reasoning chain
before it requests approval for a state-modifying action.

Usage:
    tracer = ToolCallTracer()

    # Before tool execution
    tracer.start_call("get_factory_config", {"factory": "Factory B"})

    # After tool execution
    tracer.end_call(result_data)

    # When creating approval
    trace = tracer.get_trace()
    # -> [{"tool_name": "get_factory_config", "arguments": {...}, "response_summary": "...", ...}]
"""
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC


class ToolCallTracer:
    """Tracks tool calls for audit trail and HIL drawer context display"""

    def __init__(self):
        self.trace: List[Dict[str, Any]] = []
        self._current_call: Optional[Dict[str, Any]] = None

    def start_call(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Start tracking a tool call"""
        self._current_call = {
            "tool_name": tool_name,
            "arguments": arguments,
            "start_time_ms": int(time.time() * 1000),
            "timestamp": datetime.now(UTC).isoformat()
        }

    def end_call(
        self,
        result: Any,
        error: Optional[str] = None,
        response_summary_max_chars: int = 200
    ) -> None:
        """
        Complete the current tool call with result or error

        Args:
            result: The tool's return value (dict, string, etc.)
            error: Error message if tool failed
            response_summary_max_chars: Max length for response summary
        """
        if not self._current_call:
            print("Warning: end_call() without start_call()")
            return

        end_time_ms = int(time.time() * 1000)
        duration_ms = end_time_ms - self._current_call["start_time_ms"]

        # Create summary of response
        if error:
            response_summary = f"ERROR: {error}"
        elif isinstance(result, dict):
            # For dict responses, show key fields
            summary_parts = []
            for key, value in list(result.items())[:5]:  # First 5 keys
                if isinstance(value, (str, int, float, bool)):
                    summary_parts.append(f"{key}: {value}")
                elif isinstance(value, list):
                    summary_parts.append(f"{key}: [{len(value)} items]")
                else:
                    summary_parts.append(f"{key}: {type(value).__name__}")
            response_summary = "{" + ", ".join(summary_parts) + "}"
        elif isinstance(result, str):
            response_summary = result
        else:
            response_summary = str(result)

        # Truncate if too long
        if len(response_summary) > response_summary_max_chars:
            response_summary = response_summary[:response_summary_max_chars - 3] + "..."

        # Complete the call record
        self._current_call["duration_ms"] = duration_ms
        self._current_call["response_summary"] = response_summary
        self._current_call["success"] = error is None

        # Remove start_time_ms (internal only)
        del self._current_call["start_time_ms"]

        # Add to trace
        self.trace.append(self._current_call)
        self._current_call = None

    def get_trace(self) -> List[Dict[str, Any]]:
        """
        Get the complete tool call trace

        Returns:
            List of tool call records, each with:
            - tool_name: str
            - arguments: dict
            - timestamp: ISO datetime
            - duration_ms: int
            - response_summary: str
            - success: bool
        """
        return self.trace.copy()

    def clear(self) -> None:
        """Clear the trace (e.g., for new session)"""
        self.trace = []
        self._current_call = None

    def get_trace_count(self) -> int:
        """Get number of completed tool calls"""
        return len(self.trace)
