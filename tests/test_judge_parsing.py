"""
Tests for LLM Judge grading parser resilience in evaluation/judge.py:
- Parses markdown code fences (```json ... ```)
- Parses JSON with reasoning chatter
- Handles regex fallback for unquoted keys / malformed JSON
- Clamps scores between 1 and 10
"""

import pytest
from evaluation.judge import _extract_json, _clamp


def test_extract_json_standard():
    text = '{"relevance": 9, "accuracy": 8, "clarity": 9, "comment": "Excellent report."}'
    data = _extract_json(text)
    assert data["relevance"] == 9
    assert data["accuracy"] == 8
    assert data["clarity"] == 9
    assert data["comment"] == "Excellent report."


def test_extract_json_with_markdown_fences():
    text = (
        "Here is my evaluation of the report:\n\n"
        "```json\n"
        '{\n  "relevance": 8,\n  "accuracy": 7,\n  "clarity": 9,\n  "comment": "Solid analysis with good citations."\n}\n'
        "```\n"
        "Hope this helps!"
    )
    data = _extract_json(text)
    assert data["relevance"] == 8
    assert data["accuracy"] == 7
    assert data["clarity"] == 9


def test_extract_json_with_reasoning_tokens():
    text = (
        "<think>\nThe topic was quantum computing. The report thoroughly covers qubits and error correction.\n"
        "Accuracy is high based on verified sources.\n</think>\n\n"
        '{"relevance": 10, "accuracy": 9, "clarity": 8, "comment": "Outstanding technical depth."}'
    )
    data = _extract_json(text)
    assert data["relevance"] == 10
    assert data["accuracy"] == 9
    assert data["clarity"] == 8


def test_extract_json_regex_fallback():
    # Malformed JSON with missing quotes around keys or trailing comma
    text = (
        "Evaluation summary:\n"
        "relevance: 8\n"
        "accuracy: 9\n"
        "clarity: 7\n"
        'comment: "Good synthesis overall"'
    )
    data = _extract_json(text)
    assert data["relevance"] == 8
    assert data["accuracy"] == 9
    assert data["clarity"] == 7
    assert "Good synthesis overall" in data["comment"]


def test_clamp_values():
    assert _clamp(12) == 10
    assert _clamp(0) == 1
    assert _clamp(-5) == 1
    assert _clamp(8.4) == 8
    assert _clamp(8.7) == 9
