# This project was developed with assistance from AI tools.
"""Dwell-based state machine for VLM verdicts.

Single-frame VLM hiccups shouldn't wake up Fleet Manager. A verdict has to
persist for `dwell_frames` consecutive observations before we flip state and
emit an alert.

Kept as its own module (no Kafka/httpx deps) so the algorithm is trivially
unit-testable without the rest of the service environment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DebounceState:
    dwell_frames: int
    obstructed: bool | None = None
    pending: bool | None = None
    pending_count: int = 0

    def observe(self, verdict: bool) -> bool:
        """Update state; return True when the caller should emit an alert.

        - Initial state (`obstructed is None`): the first run of `dwell_frames`
          matching verdicts establishes the baseline and fires once so
          downstream consumers know the steady-state.
        - Established state: a different verdict starts a pending counter; the
          state flips and fires when the counter reaches `dwell_frames`.
        - Same-as-current verdict: resets the pending counter, no fire.
        """
        if verdict == self.obstructed:
            self.pending = None
            self.pending_count = 0
            return False
        if verdict != self.pending:
            self.pending = verdict
            self.pending_count = 1
        else:
            self.pending_count += 1
        if self.pending_count >= self.dwell_frames:
            self.obstructed = verdict
            self.pending = None
            self.pending_count = 0
            return True
        return False
