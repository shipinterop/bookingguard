"""LLM-based structured extraction using OpenAI API.

Extracts CandidateFacts from free-form documents.
Never directly produces the final business verdict.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from bookingguard.domain.models import (
    Action,
    CandidateFact,
    Document,
    EvidenceRef,
    ExecutionMode,
    ProcessingStatus,
    Scope,
    ValueRole,
)
from bookingguard.extract.base import ExtractionResult

SYSTEM_PROMPT = """\
You are a maritime document analyst. Extract booking change facts from the document.

Return a JSON object with this structure:
{
  "booking_reference": "string or null",
  "carrier": "string or null",
  "revision": "string or null",
  "changes": [
    {
      "field_name": "cy_cutoff",
      "value": "ISO 8601 datetime with timezone",
      "value_role": "current | old | proposed | conditional | unknown",
      "action": "set | clear | unchanged | uncertain",
      "scope": {
        "type": "booking_all | container | leg",
        "container_reference": "string or null"
      },
      "evidence": {
        "block_id": "block ID from the document",
        "quote": "exact text from the document supporting this fact"
      }
    }
  ],
  "unresolved_items": ["list of items you could not determine"]
}

Rules:
- Use exact quotes from the document. Do NOT generate offset numbers.
- If you cannot determine value_role, use "unknown".
- If you cannot determine action, use "uncertain".
- If you cannot determine scope, use {"type": "unknown"}.
- Proposed or pending-approval values must have value_role "proposed", NOT "current".
- Container-specific changes must have scope type "container".
- Do NOT guess timezone. If timezone is missing, include the value as-is.
"""


class LLMExtractor:
    """Extracts facts from documents using OpenAI API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.timeout = timeout

    def extract(self, document: Document) -> ExtractionResult:
        if not self.api_key:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                unresolved_items=["OPENAI_API_KEY not configured."],
            )

        try:
            import openai
        except ImportError:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                unresolved_items=["openai package not installed."],
            )

        # Build user message from document blocks
        user_content = f"Document: {document.filename}\n\n"
        for block in document.blocks:
            user_content += f"[{block.block_id}]\n{block.text}\n\n"

        start = time.monotonic()
        try:
            client = openai.OpenAI(api_key=self.api_key, timeout=self.timeout)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            latency = (time.monotonic() - start) * 1000
        except Exception as e:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                provider="openai",
                model_id=self.model,
                latency_ms=(time.monotonic() - start) * 1000,
                unresolved_items=[f"API call failed: {e}"],
            )

        # Parse response
        choice = response.choices[0] if response.choices else None
        if choice is None or choice.message.content is None:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                provider="openai",
                model_id=self.model,
                latency_ms=latency,
                unresolved_items=["Empty response from API."],
            )

        # Check for refusal
        if hasattr(choice.message, "refusal") and choice.message.refusal:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                provider="openai",
                model_id=self.model,
                latency_ms=latency,
                unresolved_items=[f"Model refused: {choice.message.refusal}"],
            )

        # Parse JSON
        try:
            data = json.loads(choice.message.content)
        except json.JSONDecodeError as e:
            return ExtractionResult(
                processing_status=ProcessingStatus.FAILED,
                execution_mode=ExecutionMode.LIVE,
                provider="openai",
                model_id=self.model,
                latency_ms=latency,
                unresolved_items=[f"Invalid JSON response: {e}"],
            )

        # Build usage dict
        usage: dict[str, int] = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        # Convert to CandidateFacts
        facts = _parse_extraction_response(data, document.document_id)
        unresolved = data.get("unresolved_items", [])

        return ExtractionResult(
            candidate_facts=facts,
            unresolved_items=unresolved,
            processing_status=ProcessingStatus.COMPLETED,
            execution_mode=ExecutionMode.LIVE,
            provider="openai",
            model_id=response.model or self.model,
            usage=usage,
            latency_ms=latency,
        )


def _parse_extraction_response(
    data: dict[str, Any], document_id: str
) -> list[CandidateFact]:
    """Convert LLM JSON response to CandidateFact list."""
    facts: list[CandidateFact] = []

    # Extract identity facts
    for field, key in [
        ("booking_reference", "booking_reference"),
        ("carrier", "carrier"),
        ("revision", "revision"),
    ]:
        val = data.get(key)
        if val:
            facts.append(
                CandidateFact(
                    field_name=field,
                    value=str(val),
                    value_role=ValueRole.CURRENT,
                    action=Action.SET,
                    scope=Scope(type="booking_all"),
                    source_document_id=document_id,
                    extraction_method="llm",
                )
            )

    # Extract changes
    for change in data.get("changes", []):
        try:
            role_str = change.get("value_role", "unknown")
            try:
                role = ValueRole(role_str)
            except ValueError:
                role = ValueRole.UNKNOWN

            action_str = change.get("action", "uncertain")
            try:
                action = Action(action_str)
            except ValueError:
                action = Action.UNCERTAIN

            scope_data = change.get("scope", {})
            scope = Scope(
                type=scope_data.get("type", "unknown"),
                container_reference=scope_data.get("container_reference"),
            )

            evidence = None
            ev_data = change.get("evidence")
            if ev_data and ev_data.get("block_id") and ev_data.get("quote"):
                evidence = EvidenceRef(
                    block_id=ev_data["block_id"],
                    quote=ev_data["quote"],
                )

            facts.append(
                CandidateFact(
                    field_name=change.get("field_name", "unknown"),
                    value=str(change.get("value", "")),
                    value_role=role,
                    action=action,
                    scope=scope,
                    source_document_id=document_id,
                    extraction_method="llm",
                    evidence=evidence,
                )
            )
        except (KeyError, TypeError):
            continue

    return facts
