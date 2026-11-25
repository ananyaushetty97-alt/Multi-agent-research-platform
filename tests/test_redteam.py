"""Offline check of the red-team harness: python tests/test_redteam.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from redteam import run_redteam as rt  # noqa: E402

import pytest  # noqa: E402

os.environ.setdefault("TAVILY_API_KEY", "offline-dummy")
failed = 0


@pytest.fixture(autouse=True, scope="module")
def fake_llm():
    """Install the gullible fake LLM for these tests only, then put the real pieces back,
    so other test files in the same pytest run are not affected."""
    import agents.summarize_agent as s
    import agents.verify_agent as v
    import agents.write_agent as w
    import evaluation.judge as j
    import guardrails.checks as gc
    saved = {
        "s": s.call_llm, "v": v.call_llm, "w": w.call_llm, "j": getattr(j, "call_llm", None),
        "guards": gc.USE_LLM_GUARDS, "offline": getattr(rt, "OFFLINE_TEST_MODE", None),
    }
    rt.install_fake_llm()
    yield
    s.call_llm = saved["s"]
    v.call_llm = saved["v"]
    w.call_llm = saved["w"]
    if saved["j"] is None:
        del j.call_llm
    else:
        j.call_llm = saved["j"]
    gc.USE_LLM_GUARDS = saved["guards"]
    if saved["offline"] is not None:
        rt.OFFLINE_TEST_MODE = saved["offline"]


def check(name, ok):
    global failed
    print(("  PASS  " if ok else "  FAIL  ") + name)
    failed += not ok


def test_redteam_indirect_leak_and_defense():
    undefended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=False)
    assert undefended["canary_leaked"] and undefended["reached_user"]
    defended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=True)
    assert not defended["reached_user"]


def test_redteam_direct_jailbreaks_blocked():
    direct = [rt.run_direct(p) for p in rt.DIRECT_PAYLOADS]
    assert all(r["input_blocked"] for r in direct)


if __name__ == "__main__":
    rt.install_fake_llm()
    undefended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=False)
    check("without defense, a gullible LLM leaks the canary (harness detects it)",
          undefended["canary_leaked"] and undefended["reached_user"])
    defended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=True)
    check("with defense, the canary never reaches the user", not defended["reached_user"])
    direct = [rt.run_direct(p) for p in rt.DIRECT_PAYLOADS]
    check("input guard blocks every direct jailbreak", all(r["input_blocked"] for r in direct))
    try:
        target, Message = rt.make_pyrit_target()
        row = rt.send_via_pyrit(target, Message, "direct", rt.DIRECT_PAYLOADS[0])
        check("attacks can be sent through PyRIT", row["input_blocked"])
    except (ImportError, ModuleNotFoundError):
        print("  SKIP  attacks can be sent through PyRIT (pyrit not installed in venv; see requirements-redteam.txt)")
    print(f"\n=== {'all passed' if not failed else f'{failed} failed'} ===")
    sys.exit(1 if failed else 0)
