"""Offline check of the red-team harness: python tests/test_redteam.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from redteam import run_redteam as rt  # noqa: E402

os.environ.setdefault("TAVILY_API_KEY", "offline-dummy")
rt.install_fake_llm()
failed = 0


def check(name, ok):
    global failed
    print(("  PASS  " if ok else "  FAIL  ") + name)
    failed += not ok


undefended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=False)
check("without defense, a gullible LLM leaks the canary (harness detects it)",
      undefended["canary_leaked"] and undefended["reached_user"])
defended = rt.run_indirect(rt.INDIRECT_PAYLOADS[0], defense=True)
check("with defense, the canary never reaches the user", not defended["reached_user"])
direct = [rt.run_direct(p) for p in rt.DIRECT_PAYLOADS]
check("input guard blocks every direct jailbreak", all(r["input_blocked"] for r in direct))
target, Message = rt.make_pyrit_target()
row = rt.send_via_pyrit(target, Message, "direct", rt.DIRECT_PAYLOADS[0])
check("attacks can be sent through PyRIT", row["input_blocked"])
print(f"\n=== {'all passed' if not failed else f'{failed} failed'} ===")
sys.exit(1 if failed else 0)
