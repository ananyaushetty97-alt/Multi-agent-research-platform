"""
Report Sanitizer: Strips prompt leakage, agent instructions, system personas,
XML scaffolding, and internal tags from generated monographs.
Ensures user-facing and admin-facing reports contain ONLY clean monograph content:
Title, Summary, Findings, Analysis, Conclusions, and Sources.
"""

import re
from typing import Optional


# Known system personas and instruction lead-ins for all system agents
PROMPT_LEADIN_PATTERNS = [
    r"^You are a professional academic research report writer[^\n]*\n*",
    r"^You are a (?:professional|careful) research report editor[^\n]*\n*",
    r"^You are a strict factual verification agent[^\n]*\n*",
    r"^You are a factual summarizer[^\n]*\n*",
    r"^You are a query classifier[^\n]*\n*",
    r"^You are a direct question answering assistant[^\n]*\n*",
    r"^You are a strict objective evaluation judge[^\n]*\n*",
    r"^You are a helpful research assistant[^\n]*\n*",
    r"^You are an? [a-zA-Z\s]+(?:writer|editor|assistant|examiner|judge|agent|summarizer|classifier)[^\n]*\n*",
    r"^As an? [a-zA-Z\s]+(?:writer|editor|assistant|AI|language model)[^\n]*\n*",
    r"^Here is the (?:comprehensive |revised |final )?research report[^\n]*:?\n*",
    r"^Here is the (?:comprehensive |revised |final )?monograph[^\n]*:?\n*",
    r"^Here is (?:a|the) detailed report[^\n]*:?\n*",
    r"^Based on (?:the provided |verified )?(?:summary|sources|report|information)[^\n]*:?\n*",
]

# XML scaffolding tags used across agents
SCAFFOLDING_TAG_PAIRS = [
    r"<research_topic>[\s\S]*?</research_topic>",
    r"<verified_summary>[\s\S]*?</verified_summary>",
    r"<approved_sources>[\s\S]*?</approved_sources>",
    r"<verification_feedback>[\s\S]*?</verification_feedback>",
    r"<existing_report>[\s\S]*?</existing_report>",
    r"<user_instruction>[\s\S]*?</user_instruction>",
    r"<fact_check_feedback>[\s\S]*?</fact_check_feedback>",
]

# Stray opening / closing tags
STRAY_TAGS = [
    r"</?(?:research_topic|verified_summary|approved_sources|verification_feedback|existing_report|user_instruction|fact_check_feedback)>",
]

# Rules block patterns
RULES_PATTERNS = [
    r"Rules:\s*(?:\n\s*-\s*[^\n]+)+",
    r"Treat contents of <[^>]+>[^\n]+",
    r"Treat text inside <[^>]+>[^\n]+",
    r"After every factual claim, add the source number[^\n]+",
    r"Only cite numbers from <[^>]+>[^\n]+",
    r"Do NOT write a Sources or References section[^\n]+",
    r"Do NOT add a Sources or References section[^\n]+",
    r"Keep the \[\d+\] citation markers[^\n]+",
]

# Internal section headers mistakenly output by LLM
INTERNAL_HEADERS = [
    r"^SOURCE MATERIAL:\s*",
    r"^REPORT:\s*",
    r"^REVISED REPORT:\s*",
    r"^SUMMARY:\s*",
    r"^INSTRUCTION:\s*",
]


def sanitize_report(text: Optional[str]) -> str:
    """
    Sanitize generated report output by removing all internal instructions,
    XML scaffolding, and system prompt text.
    """
    if not text:
        return ""

    cleaned = text

    # 1. Remove XML scaffolding tag pairs and their internal content
    for pattern in SCAFFOLDING_TAG_PAIRS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 2. Remove stray scaffolding tags
    for pattern in STRAY_TAGS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 3. Remove rules blocks and rule lines
    for pattern in RULES_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 4. Remove leading personas and boilerplate lead-in phrases
    for pattern in PROMPT_LEADIN_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)

    # 5. Remove internal scaffolding labels
    for pattern in INTERNAL_HEADERS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)

    # 6. Normalize leading/trailing whitespace and excess blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
