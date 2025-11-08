from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from models.a2a import A2AMessage, Artifact, MessagePart, TaskResult, TaskStatus

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from google import genai  # type: ignore
except Exception:  # pragma: no cover - gracefully handle missing package
    genai = None  # type: ignore

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Log which model is being used at startup
logger.info(f"Gemini client initialized with model: {GEMINI_MODEL}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_prompt(subject: str, price_snapshot: dict[str, Any], news_summary: str) -> str:
    return (
        "You are an expert financial analyst specializing in cryptocurrency and forex markets.\n\n"
        f"**Asset to Analyze:** {subject}\n"
        f"**Current Price Data:** {price_snapshot}\n"
        f"**Recent News Headlines:**\n{news_summary}\n\n"
        "**Task:** Provide a comprehensive market analysis in strict JSON format.\n\n"
        "**Analysis Framework:**\n"
        "1. Assess market sentiment from news (bullish/bearish signals)\n"
        "2. Evaluate price action and trends\n"
        "3. Consider macro factors (regulations, adoption, economic indicators)\n"
        "4. Identify risks and catalysts\n"
        "5. Synthesize into actionable insights\n\n"
        "**Required JSON Output:**\n"
        "{\n"
        '  "impact_score": <float between -1.0 and 1.0>,  // -1=very bearish, 0=neutral, +1=very bullish\n'
        '  "direction": <"bullish"|"bearish"|"neutral">,\n'
        '  "confidence": <float 0-1>,  // 0=low confidence, 1=high confidence\n'
        '  "reasoning": [<list of 3-5 concise bullet points explaining your analysis>],\n'
        '  "key_factors": [<2-3 most important factors driving the analysis>],\n'
        '  "risks": [<1-2 main risks to the thesis>],\n'
        '  "timeframe": <"short-term"|"medium-term"|"long-term">  // investment horizon\n'
        "}\n\n"
        "Return ONLY valid JSON (no markdown, no commentary)."
    )


def _parse_model_output(raw_text: str) -> dict[str, Any]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _coerce_reasoning(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _default_analysis(news_summary: str) -> dict[str, Any]:
    score = 0.0
    reasoning: list[str] = []
    lowered = news_summary.lower()
    if "rate cut" in lowered:
        score += 0.15
        reasoning.append("rate cut mention detected")
    if "rate hike" in lowered:
        score -= 0.15
        reasoning.append("rate hike mention detected")
    return {
        "impact_score": max(min(score, 1.0), -1.0),
        "direction": "bullish" if score > 0 else "bearish" if score < 0 else "neutral",
        "confidence": 0.25,
        "reasoning": reasoning or ["rule-based fallback"],
    }


def _generate_with_gemini(prompt: str, timeout: int) -> dict[str, Any]:
    if not GEMINI_API_KEY or genai is None:
        return {}
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
    except Exception as exc:
        error_message = str(exc)
        
        if "RESOURCE_EXHAUSTED" in error_message or "429" in error_message or "quota" in error_message.lower():
            # Return special marker to indicate quota exhaustion
            return {"quota_exceeded": True}
        
        return {}

    collected: list[str] = []
    try:
        if hasattr(response, 'text'):
            collected.append(response.text)
        elif hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content'):
                    content = candidate.content
                    if hasattr(content, 'parts'):
                        for part in content.parts:
                            if hasattr(part, 'text'):
                                collected.append(part.text)
    except Exception:
        return {}

    return _parse_model_output("".join(collected))


def analyze_sync(subject: str, price_snapshot: dict[str, Any], news_summary: str, timeout: int = 20) -> TaskResult:
    prompt = _build_prompt(subject, price_snapshot, news_summary)
    payload = _generate_with_gemini(prompt, timeout)

    if not payload:
        payload = _default_analysis(news_summary)

    reasoning = _coerce_reasoning(payload.get("reasoning"))
    analysis = {
        "impact_score": float(payload.get("impact_score", 0.0)),
        "direction": str(payload.get("direction", "neutral")),
        "confidence": float(payload.get("confidence", 0.0)),
        "reasoning": reasoning,
    }

    message = A2AMessage(
        role="agent",
        parts=[
            MessagePart(kind="text", text="Gemini analysis complete."),
            MessagePart(
                kind="data",
                data={
                    "analysis": analysis,
                    "subject": subject,
                    "price_snapshot": price_snapshot,
                    "timestamp": _utc_now(),
                },
            ),
        ],
    )

    status = TaskStatus(state="completed", message=message)

    artifact = Artifact(name=f"Gemini analysis for {subject}", parts=message.parts)

    task_id = f"analysis-{uuid4()}"
    context_id = f"context-{subject.lower().replace(' ', '-')}"

    return TaskResult(
        taskId=task_id,
        contextId=context_id,
        status=status,
        artifacts=[artifact],
        history=[message],
    )


def generate_text_sync(prompt: str, temperature: float = 0.7, timeout: int = 10) -> str:
    """
    Generate text using Gemini for simple prompt completions.
    
    Args:
        prompt: The prompt text
        temperature: Controls randomness (0.0 = deterministic, 1.0 = creative)
        timeout: Request timeout in seconds
    
    Returns:
        Generated text, or empty string on failure
    """
    if not GEMINI_API_KEY or genai is None:
        return ""
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={"temperature": temperature}
        )
        
        # Extract text from response
        if hasattr(response, 'text'):
            return response.text
        elif hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content'):
                    content = candidate.content
                    if hasattr(content, 'parts'):
                        for part in content.parts:
                            if hasattr(part, 'text'):
                                return part.text
        return ""
        
    except Exception as exc:
        # Silently fail for simple text generation
        return ""
