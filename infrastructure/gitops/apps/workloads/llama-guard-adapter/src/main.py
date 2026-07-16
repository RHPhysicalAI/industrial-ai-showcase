# This project was developed with assistance from AI tools.
"""
Llama Guard Moderation Adapter

Provides OpenAI-compatible /v1/moderations endpoint backed by Llama Guard 3-8B via vLLM.
Implements strict fail-closed parsing: malformed outputs are treated as unsafe.
"""
import logging
import os
import time
from typing import List, Dict, Any, Union

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Llama Guard Moderation Adapter", version="1.0.0")

# Configuration
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://llama-guard:8000")
VLLM_MODEL = os.getenv("VLLM_MODEL", "meta-llama/Llama-Guard-3-8B")
VLLM_TIMEOUT = float(os.getenv("VLLM_TIMEOUT", "30.0"))
API_KEY = os.getenv("API_KEY")  # Optional API key for this service

# Llama Guard 3 taxonomy (pinned version)
LLAMA_GUARD_CATEGORIES = {
    "S1": {"code": "S1", "name": "Violent Crimes", "description": "Responses that enable, encourage, or endorse the commission of violent crimes"},
    "S2": {"code": "S2", "name": "Non-Violent Crimes", "description": "Responses that enable, encourage, or endorse the commission of non-violent crimes"},
    "S3": {"code": "S3", "name": "Sex-Related Crimes", "description": "Responses that enable, encourage, or endorse the commission of sex-related crimes"},
    "S4": {"code": "S4", "name": "Child Sexual Exploitation", "description": "Responses that contain, describe, enable, encourage, or endorse the sexual abuse of children"},
    "S5": {"code": "S5", "name": "Defamation", "description": "Responses that are both verifiably false and likely to injure a living person's reputation"},
    "S6": {"code": "S6", "name": "Specialized Advice", "description": "Responses that contain specialized financial, medical, or legal advice"},
    "S7": {"code": "S7", "name": "Privacy", "description": "Responses that contain sensitive, nonpublic personal information that could undermine someone's physical, digital, or financial security"},
    "S8": {"code": "S8", "name": "Intellectual Property", "description": "Responses that may violate the intellectual property rights of any third party"},
    "S9": {"code": "S9", "name": "Indiscriminate Weapons", "description": "Responses that enable, encourage, or endorse the creation of indiscriminate weapons"},
    "S10": {"code": "S10", "name": "Hate", "description": "Responses that demean or dehumanize people on the basis of their sensitive, personal characteristics"},
    "S11": {"code": "S11", "name": "Suicide & Self-Harm", "description": "Responses that enable, encourage, or endorse acts of intentional self-harm"},
    "S12": {"code": "S12", "name": "Sexual Content", "description": "Responses that contain erotica"},
    "S13": {"code": "S13", "name": "Elections", "description": "Responses that contain factually incorrect information about electoral systems and processes"},
}

# Map Llama Guard categories to OpenAI-compatible categories
# OpenAI uses: hate, hate/threatening, harassment, harassment/threatening, self-harm,
# self-harm/intent, self-harm/instructions, sexual, sexual/minors, violence, violence/graphic
CATEGORY_MAPPING = {
    "S1": "violence",
    "S2": "harassment",
    "S3": "sexual",
    "S4": "sexual/minors",
    "S5": "harassment",
    "S6": "harassment",  # Specialized advice -> general harassment
    "S7": "harassment",  # Privacy violations
    "S8": "harassment",  # IP violations
    "S9": "violence",    # Weapons
    "S10": "hate",
    "S11": "self-harm",
    "S12": "sexual",
    "S13": "harassment",  # Election misinformation
}


class ModerationRequest(BaseModel):
    """OpenAI-compatible moderation request"""
    input: Union[str, List[str]] = Field(..., description="Text to moderate (string or array)")
    model: str = Field(default="text-moderation-latest", description="Model to use (ignored)")


class ModerationResult(BaseModel):
    """Single moderation result"""
    flagged: bool
    categories: Dict[str, bool]
    category_scores: Dict[str, float]


class ModerationResponse(BaseModel):
    """OpenAI-compatible moderation response"""
    id: str
    model: str
    results: List[ModerationResult]


def build_llama_guard_prompt(text: str) -> List[Dict[str, str]]:
    """
    Build Llama Guard 3 chat messages using official format.

    Llama Guard chat template doesn't support system role - must use user only.
    Conversation roles must alternate user/assistant/user/assistant.
    """
    # Build category list
    category_list = "\n".join(
        f"{cat['code']}: {cat['name']}"
        for cat in LLAMA_GUARD_CATEGORIES.values()
    )

    user_message = f"""Task: Check if there is unsafe content in 'User' messages in conversations according our safety policy with the below categories.

<BEGIN UNSAFE CONTENT CATEGORIES>
{category_list}
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>

User: {text}

<END CONVERSATION>

Provide your safety assessment for User in the above conversation:
- First line must read 'safe' or 'unsafe'.
- If unsafe, a second line must include a comma-separated list of violated categories."""

    # Llama Guard template requires user/assistant alternation - use single user message
    return [
        {"role": "user", "content": user_message}
    ]


def parse_llama_guard_response(response_text: str) -> tuple[bool, List[str]]:
    """
    Parse Llama Guard response strictly.

    Expected format:
        safe
    OR:
        unsafe
        S1,S3

    Args:
        response_text: Raw text from Llama Guard

    Returns:
        (is_safe, violated_categories)

    Raises:
        ValueError: If response format is malformed (fail-closed)
    """
    lines = response_text.strip().split('\n')

    if not lines:
        raise ValueError("Empty response from Llama Guard")

    first_line = lines[0].strip().lower()

    if first_line == "safe":
        return True, []
    elif first_line == "unsafe":
        if len(lines) < 2:
            raise ValueError("Unsafe response missing category list")

        category_line = lines[1].strip()
        if not category_line:
            raise ValueError("Empty category list in unsafe response")

        # Parse comma-separated categories
        categories = [cat.strip() for cat in category_line.split(',')]

        # Validate all categories are known
        for cat in categories:
            if cat not in LLAMA_GUARD_CATEGORIES:
                raise ValueError(f"Unknown category code: {cat}")

        return False, categories
    else:
        raise ValueError(f"Invalid first line (expected 'safe' or 'unsafe'): {first_line}")


async def call_vllm(messages: List[Dict[str, str]]) -> str:
    """
    Call vLLM /v1/chat/completions endpoint.

    Args:
        messages: Chat messages in OpenAI format

    Returns:
        Response text from model

    Raises:
        HTTPException: On vLLM errors or timeouts
    """
    payload = {
        "model": VLLM_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 100,  # Llama Guard responses are short
        "top_p": 1.0,
    }

    try:
        async with httpx.AsyncClient(timeout=VLLM_TIMEOUT) as client:
            logger.info(f"Calling vLLM at {VLLM_BASE_URL}/v1/chat/completions")
            response = await client.post(
                f"{VLLM_BASE_URL}/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()

            result = response.json()

            if "choices" not in result or not result["choices"]:
                raise HTTPException(
                    status_code=502,
                    detail="vLLM returned empty choices"
                )

            return result["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        logger.error("vLLM request timed out")
        raise HTTPException(status_code=504, detail="vLLM request timed out")
    except httpx.HTTPError as e:
        logger.error(f"vLLM HTTP error: {e}")
        raise HTTPException(status_code=502, detail=f"vLLM error: {str(e)}")


async def moderate_text(text: str) -> ModerationResult:
    """
    Moderate a single text input.

    Args:
        text: Text to moderate

    Returns:
        ModerationResult

    Raises:
        HTTPException: On vLLM errors
    """
    # Build Llama Guard prompt
    messages = build_llama_guard_prompt(text)

    # Call vLLM
    start_time = time.time()
    response_text = await call_vllm(messages)
    duration = time.time() - start_time

    logger.info(f"vLLM response in {duration:.2f}s: {response_text[:100]}")

    # Parse response (strict, fail-closed)
    try:
        is_safe, violated_categories = parse_llama_guard_response(response_text)
    except ValueError as e:
        # Malformed output: treat as UNSAFE (fail-closed)
        logger.error(f"Malformed Llama Guard response: {e}. Response: {response_text}")
        logger.error("FAIL-CLOSED: Treating malformed response as unsafe")

        # Return all categories flagged with low confidence
        return ModerationResult(
            flagged=True,
            categories={cat: True for cat in CATEGORY_MAPPING.values()},
            category_scores={cat: 0.5 for cat in CATEGORY_MAPPING.values()}
        )

    if is_safe:
        # All categories safe
        return ModerationResult(
            flagged=False,
            categories={cat: False for cat in set(CATEGORY_MAPPING.values())},
            category_scores={cat: 0.0 for cat in set(CATEGORY_MAPPING.values())}
        )
    else:
        # Map violated Llama Guard categories to OpenAI categories
        openai_categories_flagged = set()
        for llama_cat in violated_categories:
            openai_cat = CATEGORY_MAPPING.get(llama_cat)
            if openai_cat:
                openai_categories_flagged.add(openai_cat)

        all_openai_cats = set(CATEGORY_MAPPING.values())

        return ModerationResult(
            flagged=True,
            categories={
                cat: (cat in openai_categories_flagged)
                for cat in all_openai_cats
            },
            category_scores={
                cat: (1.0 if cat in openai_categories_flagged else 0.0)
                for cat in all_openai_cats
            }
        )


@app.post("/v1/moderations", response_model=ModerationResponse)
async def moderate(request: ModerationRequest, req: Request):
    """
    OpenAI-compatible moderation endpoint.

    Accepts:
        {"input": "text"} or {"input": ["text1", "text2"]}

    Returns:
        {"id": "...", "model": "...", "results": [...]}
    """
    # Optional API key check
    if API_KEY:
        auth_header = req.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or auth_header[7:] != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    # Normalize input to list
    if isinstance(request.input, str):
        inputs = [request.input]
    else:
        inputs = request.input

    if not inputs:
        raise HTTPException(status_code=400, detail="Empty input")

    logger.info(f"Moderating {len(inputs)} input(s)")

    # Moderate each input
    results = []
    for text in inputs:
        result = await moderate_text(text)
        results.append(result)

    # Generate response ID
    response_id = f"modr-{int(time.time() * 1000)}"

    return ModerationResponse(
        id=response_id,
        model=VLLM_MODEL,
        results=results
    )


@app.get("/health")
async def health():
    """Health check endpoint"""
    try:
        # Quick check that vLLM is reachable
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VLLM_BASE_URL}/health")
            response.raise_for_status()

        return {
            "status": "healthy",
            "vllm_url": VLLM_BASE_URL,
            "vllm_model": VLLM_MODEL,
            "vllm_status": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"vLLM not available: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Llama Guard Moderation Adapter",
        "version": "1.0.0",
        "endpoints": {
            "moderation": "POST /v1/moderations",
            "health": "GET /health"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
