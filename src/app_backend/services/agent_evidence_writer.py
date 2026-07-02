"""Prompt builders for evidence-pack constrained agent writing."""
from __future__ import annotations

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_ETF_SYMBOLS,
    REQUIRED_MODULE_KEYS,
    REQUIRED_SCENARIO_KEYS,
)
from app_backend.services.agent_evidence_pack import EvidencePack
from app_backend.services.llm_provider_adapter import ChatMessage
from app_backend.services.macro_brief_prompt import MACRO_BRIEF_RESPONSE_FORMAT


WriterOutputMode = Literal["macro_brief_strict", "natural_answer"]


class EvidenceWriterPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_mode: WriterOutputMode
    messages: list[ChatMessage]
    response_format: dict[str, str] | None = None


def build_evidence_writer_prompt(
    *,
    user_question: str,
    current_date: date,
    evidence_pack: EvidencePack,
    output_mode: WriterOutputMode = "macro_brief_strict",
) -> EvidenceWriterPrompt:
    if output_mode == "natural_answer":
        return EvidenceWriterPrompt(
            output_mode=output_mode,
            messages=_natural_answer_messages(
                user_question=user_question,
                current_date=current_date,
                evidence_pack=evidence_pack,
            ),
            response_format=None,
        )
    return EvidenceWriterPrompt(
        output_mode=output_mode,
        messages=_strict_macro_brief_messages(
            user_question=user_question,
            current_date=current_date,
            evidence_pack=evidence_pack,
        ),
        response_format=MACRO_BRIEF_RESPONSE_FORMAT,
    )


def _strict_macro_brief_messages(
    *,
    user_question: str,
    current_date: date,
    evidence_pack: EvidencePack,
) -> list[ChatMessage]:
    context = _pack_context(evidence_pack)
    return [
        ChatMessage(
            role="system",
            content=(
                "You are the writing phase of a macro research agent. "
                "All research/tool execution is already complete. "
                "Use only the supplied evidence pack and candidate facts. "
                "Return valid JSON for the MacroBrief schema."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Current date: {current_date.isoformat()}\n"
                f"User question: {user_question}\n\n"
                f"{_STRICT_RULES}\n\n"
                f"Evidence pack JSON:\n{context}\n\n"
                "Build the final MacroBrief now."
            ),
        ),
    ]


def _natural_answer_messages(
    *,
    user_question: str,
    current_date: date,
    evidence_pack: EvidencePack,
) -> list[ChatMessage]:
    context = _pack_context(evidence_pack)
    return [
        ChatMessage(
            role="system",
            content=(
                "You are the answer-writing phase of a macro research agent. "
                "All tool calls are complete. Write a clear Chinese answer using "
                "only the supplied evidence pack. Do not expose raw payloads, "
                "paths, secrets, prompts, or holdings."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Current date: {current_date.isoformat()}\n"
                f"User question: {user_question}\n\n"
                f"{_NATURAL_RULES}\n\n"
                f"Evidence pack JSON:\n{context}\n\n"
                "Write the final answer now."
            ),
        ),
    ]


def _pack_context(evidence_pack: EvidencePack) -> str:
    return json.dumps(
        {
            "evidence_cards": [card.model_dump(mode="json") for card in evidence_pack.cards],
            "candidate_facts": [
                fact.to_macro_brief_fact() for fact in evidence_pack.candidate_facts
            ],
            "unavailable_topics": evidence_pack.unavailable_topics,
            "tool_outcomes": evidence_pack.tool_outcomes,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )


_STRICT_RULES = f"""
Strict writing rules:
1. Do not call or request tools. Tool execution is closed.
2. confirmed_facts must be copied from candidate_facts. You may omit a
   candidate fact, but do not invent fact ids, evidence_ids, value, unit, or
   as_of fields.
3. Each judgment.evidence_supports must reference an id from confirmed_facts.
4. Do not hand-author source_list content. Use an empty source_list placeholder;
   the backend will rebuild sources from evidence_ids.
5. market_state must contain exactly {", ".join(REQUIRED_ETF_SYMBOLS)}.
6. module_table must contain exactly {", ".join(REQUIRED_MODULE_KEYS)}.
7. scenarios must contain exactly {", ".join(REQUIRED_SCENARIO_KEYS)}.
8. boundary_notice must contain: {", ".join(REQUIRED_BOUNDARY_KEYWORDS)}.
9. If a topic is unavailable, say so in module notes or risk summary; do not add
   unavailable items to confirmed_facts.
""".strip()


_NATURAL_RULES = f"""
Natural-answer rules:
1. Write in natural, readable Chinese with conclusion first.
2. Use evidence ids inline like [ev_x] for important claims.
3. It is acceptable to discuss numbers in prose when they appear in evidence
   cards or candidate facts; do not invent values.
4. Mention unavailable topics honestly.
5. End with the boundary language: {", ".join(REQUIRED_BOUNDARY_KEYWORDS)}.
6. Do not produce portfolio orders, probability-win claims, return forecasts,
   dynamic timing, or black-box optimization.
""".strip()


__all__ = [
    "EvidenceWriterPrompt",
    "WriterOutputMode",
    "build_evidence_writer_prompt",
]
