# This project was developed with assistance from AI tools.
"""
Content Moderation Client

Provides fail-closed moderation for input/output validation using Llama Guard.
Implements strict error handling, timeouts, and observability.
"""
import httpx
import logging
import time
from typing import Dict, List, Optional
from enum import Enum
import os

logger = logging.getLogger(__name__)

# Configuration
MODERATION_ENDPOINT = os.getenv(
    "MODERATION_ENDPOINT",
    "http://llama-guard-adapter.agentic-ops.svc.cluster.local:8080/v1/moderations"
)
MODERATION_TIMEOUT = float(os.getenv("MODERATION_TIMEOUT", "10.0"))  # 10 second timeout
MODERATION_MAX_RETRIES = int(os.getenv("MODERATION_MAX_RETRIES", "2"))
MODERATION_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"


class ModerationDecision(Enum):
    """Moderation decision outcomes"""
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ERROR = "error"  # Fail-closed: treat errors as blocked


class ModerationResult:
    """Result of a moderation check"""

    def __init__(
        self,
        decision: ModerationDecision,
        flagged: bool,
        categories: Dict[str, bool],
        category_scores: Dict[str, float],
        latency_ms: float,
        error: Optional[str] = None
    ):
        self.decision = decision
        self.flagged = flagged
        self.categories = categories
        self.category_scores = category_scores
        self.latency_ms = latency_ms
        self.error = error

    def is_allowed(self) -> bool:
        """Check if content is allowed (fail-closed)"""
        return self.decision == ModerationDecision.ALLOWED

    def get_blocked_categories(self) -> List[str]:
        """Get list of blocked category names"""
        return [cat for cat, flagged in self.categories.items() if flagged]

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging"""
        return {
            "decision": self.decision.value,
            "flagged": self.flagged,
            "blocked_categories": self.get_blocked_categories(),
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error
        }


class ModerationClient:
    """
    Client for content moderation with fail-closed error handling.

    Principles:
    - Never default errors to "safe"
    - Timeout or outage = blocked
    - Malformed response = blocked
    - Unknown categories = blocked
    - Log decisions without storing sensitive content
    """

    def __init__(
        self,
        endpoint: str = MODERATION_ENDPOINT,
        timeout: float = MODERATION_TIMEOUT,
        max_retries: int = MODERATION_MAX_RETRIES,
        enabled: bool = MODERATION_ENABLED
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.enabled = enabled

        # Connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        logger.info(
            f"Moderation client initialized: endpoint={endpoint}, "
            f"timeout={timeout}s, enabled={enabled}"
        )

    async def moderate(
        self,
        content: str,
        context: str = "input"  # "input" or "output"
    ) -> ModerationResult:
        """
        Moderate content with fail-closed error handling.

        Args:
            content: Text to moderate (NOTE: truncated in logs for privacy)
            context: Context for logging ("input" or "output")

        Returns:
            ModerationResult with decision (ALLOWED or BLOCKED/ERROR)
        """
        if not self.enabled:
            logger.debug(f"Moderation disabled, allowing {context}")
            return ModerationResult(
                decision=ModerationDecision.ALLOWED,
                flagged=False,
                categories={},
                category_scores={},
                latency_ms=0.0
            )

        start_time = time.time()

        # Log context without full content (privacy)
        logger.info(f"Moderating {context} (length: {len(content)} chars)")

        # Try with retries
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.post(
                    self.endpoint,
                    json={"input": content},
                    headers={"Content-Type": "application/json"}
                )

                latency_ms = (time.time() - start_time) * 1000

                # Check HTTP status
                if response.status_code != 200:
                    error_msg = f"Moderation API returned {response.status_code}"
                    logger.error(f"{error_msg} (attempt {attempt}/{self.max_retries})")
                    last_error = error_msg

                    if attempt < self.max_retries:
                        await self._backoff(attempt)
                        continue
                    else:
                        # FAIL CLOSED: HTTP error = blocked
                        return self._error_result(error_msg, latency_ms)

                # Parse response
                try:
                    data = response.json()
                except Exception as e:
                    error_msg = f"Failed to parse moderation response: {e}"
                    logger.error(error_msg)
                    # FAIL CLOSED: malformed JSON = blocked
                    return self._error_result(error_msg, latency_ms)

                # Validate response structure
                if "results" not in data or not data["results"]:
                    error_msg = "Moderation response missing 'results'"
                    logger.error(error_msg)
                    # FAIL CLOSED: malformed response = blocked
                    return self._error_result(error_msg, latency_ms)

                result = data["results"][0]

                # Extract fields with validation
                flagged = result.get("flagged", True)  # Default to flagged if missing
                categories = result.get("categories", {})
                category_scores = result.get("category_scores", {})

                # Validate categories are known (fail-closed on unknown)
                if not self._validate_categories(categories):
                    error_msg = f"Unknown categories in response: {list(categories.keys())}"
                    logger.error(error_msg)
                    # FAIL CLOSED: unknown categories = blocked
                    return self._error_result(error_msg, latency_ms)

                # Determine decision
                decision = ModerationDecision.BLOCKED if flagged else ModerationDecision.ALLOWED

                # Log decision (without sensitive content)
                blocked_cats = [cat for cat, flag in categories.items() if flag]
                logger.info(
                    f"{context.capitalize()} moderation: {decision.value} "
                    f"(flagged={flagged}, categories={blocked_cats}, latency={latency_ms:.0f}ms)"
                )

                return ModerationResult(
                    decision=decision,
                    flagged=flagged,
                    categories=categories,
                    category_scores=category_scores,
                    latency_ms=latency_ms
                )

            except httpx.TimeoutException as e:
                error_msg = f"Moderation timeout after {self.timeout}s"
                logger.error(f"{error_msg} (attempt {attempt}/{self.max_retries})")
                last_error = error_msg

                if attempt < self.max_retries:
                    await self._backoff(attempt)
                    continue

            except Exception as e:
                error_msg = f"Moderation error: {type(e).__name__}: {e}"
                logger.error(f"{error_msg} (attempt {attempt}/{self.max_retries})")
                last_error = error_msg

                if attempt < self.max_retries:
                    await self._backoff(attempt)
                    continue

        # All retries exhausted
        latency_ms = (time.time() - start_time) * 1000
        # FAIL CLOSED: all retries failed = blocked
        return self._error_result(last_error or "Unknown error", latency_ms)

    def _error_result(self, error: str, latency_ms: float) -> ModerationResult:
        """Create fail-closed error result (BLOCKED)"""
        logger.error(f"FAIL-CLOSED: Moderation error treated as BLOCKED: {error}")
        return ModerationResult(
            decision=ModerationDecision.ERROR,  # Treated as blocked
            flagged=True,  # Fail-closed
            categories={"error": True},
            category_scores={"error": 1.0},
            latency_ms=latency_ms,
            error=error
        )

    def _validate_categories(self, categories: Dict[str, bool]) -> bool:
        """Validate that all categories are known"""
        # Expected categories from Llama Guard adapter
        known_categories = {
            "violence",
            "hate",
            "harassment",
            "self-harm",
            "sexual",
            "sexual/minors",
            "error"  # Our internal error category
        }

        for cat in categories.keys():
            if cat not in known_categories:
                return False

        return True

    async def _backoff(self, attempt: int):
        """Exponential backoff between retries"""
        import asyncio
        delay = min(0.1 * (2 ** (attempt - 1)), 1.0)  # Max 1 second
        await asyncio.sleep(delay)

    async def close(self):
        """Close HTTP client connection pool"""
        await self.client.aclose()


# Global client instance
_moderation_client: Optional[ModerationClient] = None


def get_moderation_client() -> ModerationClient:
    """Get or create global moderation client instance"""
    global _moderation_client
    if _moderation_client is None:
        _moderation_client = ModerationClient()
    return _moderation_client


# Policy-safe fallback responses
BLOCKED_INPUT_RESPONSE = (
    "I cannot process this request as it violates our content policy. "
    "Please rephrase your request in a way that aligns with our safety guidelines."
)

BLOCKED_OUTPUT_RESPONSE = (
    "I apologize, but I cannot provide that response as it may violate content policies. "
    "Please try asking in a different way."
)


async def moderate_input(content: str) -> ModerationResult:
    """
    Moderate user input before sending to LLM.

    Usage:
        result = await moderate_input(user_message)
        if not result.is_allowed():
            return BLOCKED_INPUT_RESPONSE
    """
    client = get_moderation_client()
    return await client.moderate(content, context="input")


async def moderate_output(content: str) -> ModerationResult:
    """
    Moderate LLM output before returning to user.

    Usage:
        result = await moderate_output(llm_response)
        if not result.is_allowed():
            return BLOCKED_OUTPUT_RESPONSE
    """
    client = get_moderation_client()
    return await client.moderate(content, context="output")
