"""Optional LLM-powered insights via Google Gemini.

Kept isolated from GitHub/analysis code: everything here operates on a plain
structured dict handed in by the caller. Only that structured data is ever
sent to the model - never source code or raw file contents.
"""

from __future__ import annotations

import json
import os
import re

GEMINI_MODEL = "gemini-flash-latest"

_PROMPT_TEMPLATE = """You are analyzing a GitHub repository using only the structured metrics below \
(no source code is provided or available). Based solely on this data, identify strengths, \
weaknesses, and recommendations.

DATA:
{analysis_json}

Respond with strict JSON only - no markdown code fences, no commentary before or after - \
matching exactly this schema:
{{
  "strengths": ["...", "...", "..."],
  "weaknesses": ["...", "...", "..."],
  "recommendations": ["...", "...", "..."],
  "overall_assessment": "2-3 sentence summary"
}}

Requirements:
- Exactly 3 strengths, 3 weaknesses, and 3 recommendations.
- Each item is one specific, concrete sentence grounded in the data above.
- "overall_assessment" is 2-3 sentences.
"""


_QA_PROMPT_TEMPLATE = """You are answering a question about a GitHub repository using only the \
structured metrics below (no source code is provided or available). Answer solely from this data - \
if the data doesn't cover something, say so instead of guessing.

DATA:
{analysis_json}

QUESTION:
{question}

Answer in plain text (no markdown code fences), in 2-5 concise sentences grounded in the data above.
"""


class InsightsError(Exception):
    """AI insights could not be generated. Message is safe to show to users."""


def get_api_key(sidebar_value: str | None) -> str | None:
    """Resolve the Gemini API key: sidebar field takes priority over the env var."""
    return sidebar_value or os.getenv("GEMINI_API_KEY") or None


def build_prompt(analysis: dict) -> str:
    """Build the insights prompt from a structured analysis dict (JSON, no source code)."""
    return _PROMPT_TEMPLATE.format(analysis_json=json.dumps(analysis, indent=2, default=str))


def build_qa_prompt(analysis: dict, question: str) -> str:
    """Build the Q&A prompt from a structured analysis dict and a user question."""
    return _QA_PROMPT_TEMPLATE.format(
        analysis_json=json.dumps(analysis, indent=2, default=str), question=question.strip()
    )


def _get_model(api_key: str):
    """Configure the Gemini SDK and return a model instance, or raise InsightsError."""
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise InsightsError("The google-generativeai package is not installed.") from exc

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(GEMINI_MODEL)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of the model's response, tolerating stray text/fences."""
    match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in response")
    return json.loads(match.group(0))


def _validate_schema(data: dict) -> dict:
    required = {"strengths", "weaknesses", "recommendations", "overall_assessment"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"missing keys: {sorted(missing)}")
    for key in ("strengths", "weaknesses", "recommendations"):
        if not isinstance(data[key], list) or not data[key]:
            raise ValueError(f"'{key}' must be a non-empty list")
    if not isinstance(data["overall_assessment"], str) or not data["overall_assessment"].strip():
        raise ValueError("'overall_assessment' must be a non-empty string")

    return {
        "strengths": [str(item) for item in data["strengths"]],
        "weaknesses": [str(item) for item in data["weaknesses"]],
        "recommendations": [str(item) for item in data["recommendations"]],
        "overall_assessment": str(data["overall_assessment"]).strip(),
    }


def generate_insights(analysis: dict, api_key: str) -> dict:
    """Send structured analysis data to Gemini and return strengths/weaknesses/etc.

    Args:
        analysis: plain JSON-serializable dict of already-computed analysis
            (repo overview, health score breakdown, language %, activity
            stats, structure/test signals). Never pass source code here.
        api_key: Gemini API key.

    Returns:
        On success: {"ok": True, "strengths": [...], "weaknesses": [...],
        "recommendations": [...], "overall_assessment": "..."}.
        If the model's response can't be parsed as the expected JSON schema,
        degrades gracefully instead of raising: {"ok": False, "raw_text": "..."}.

    Raises:
        InsightsError: for failures that mean no response was obtained at all
            (missing dependency, bad key, network error, quota). The message
            is safe to show directly to the user.
    """
    model = _get_model(api_key)
    try:
        response = model.generate_content(build_prompt(analysis))
        text = response.text
    except Exception as exc:  # Gemini SDK raises its own exception hierarchy for auth/quota/network
        raise InsightsError(f"AI request failed: {exc}") from exc

    try:
        parsed = _validate_schema(_extract_json(text))
    except (ValueError, json.JSONDecodeError):
        return {"ok": False, "raw_text": text}

    return {"ok": True, **parsed}


def answer_question(analysis: dict, question: str, api_key: str) -> str:
    """Answer a free-form question about the repo using the already-computed analysis.

    Args:
        analysis: plain JSON-serializable dict of already-computed analysis
            (same shape as passed to generate_insights). Never pass source code here.
        question: the user's free-form question.
        api_key: Gemini API key.

    Returns:
        The model's plain-text answer.

    Raises:
        InsightsError: for failures that mean no response was obtained at all
            (missing dependency, bad key, network error, quota). The message
            is safe to show directly to the user.
    """
    model = _get_model(api_key)
    try:
        response = model.generate_content(build_qa_prompt(analysis, question))
        return response.text.strip()
    except Exception as exc:  # Gemini SDK raises its own exception hierarchy for auth/quota/network
        raise InsightsError(f"AI request failed: {exc}") from exc
