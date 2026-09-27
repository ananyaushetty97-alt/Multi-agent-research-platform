"""
Finds the team's LLM gateway (written by a teammate) so guardrails, grading
and the API can use it without caring where it lives.

It tries the usual places in order. If your teammate's function has a
different file or name, add it to CANDIDATES below.
"""
import importlib
import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
import traceback

CANDIDATES = [
    ("gateway.llm", "call_llm"),
    ("gateway.gateway", "call_llm"),
    ("gateway.llm_gateway", "call_llm"),
    ("gateway.router", "call_llm"),
    ("gateway", "call_llm"),
    ("llm_gateway", "call_llm"),
    ("agents.llm", "call_llm"),
    ("utils.llm", "call_llm"),
]

_found = None


def find_call_llm():
    global _found
    if _found is None:
        _found = (None, None)
        for module_name, fn_name in CANDIDATES:
            try:
                fn = getattr(importlib.import_module(module_name), fn_name)
                _found = (fn, f"{module_name}.{fn_name}")
                break
            except (ImportError, AttributeError) as e:
                if module_name == "gateway.llm_gateway":
                    print(f"[DEBUG] FULL TRACEBACK for {module_name}:")
                    traceback.print_exc()
                continue
    return _found


def call_llm(prompt: str) -> str:
    fn, _ = find_call_llm()
    if fn is None:
        raise RuntimeError(
            "No gateway found. Merge your teammate's gateway, or add its path "
            "to CANDIDATES in llm_link.py"
        )
    return fn(prompt)
