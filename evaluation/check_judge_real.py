"""
Are the judge's scores REAL, or made up / meaningless?

    python -m evaluation.check_judge_real            # uses the real LLM (about 8 judge calls)
    python -m evaluation.check_judge_real --fake     # offline self-test of this checker

How we decide, using reports where we already know the right answer:

  1. Good vs bad      A correct, clear report must score clearly higher than
                      reports we broke on purpose:
                        - off-topic      (well written, wrong subject)  -> low relevance
                        - wrong facts    (confident but false)          -> low accuracy
                        - jumbled        (right facts, unreadable)      -> low clarity
  2. Consistency      Grading the same report 3 times gives similar scores.
  3. Not constant     Scores actually change between reports
                      (a hardcoded or broken judge gives the same number every time).
  4. Provenance       Every score is saved with the judge's raw reply in
                      logs/scores.jsonl, so the numbers can be traced to a real LLM call.
  5. Made-up data     Looks for numbers typed into the code and shown as if real:
                      hardcoded scores in the UI, sample data the admin dashboard
                      loads at startup, and fixed (not measured) agent step times.

If 1–4 pass, the scores are real judgements. They're still one model's opinion,
not ground truth: report that honestly.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

TOPIC = "How photosynthesis works in plants"

GOOD = """# How Photosynthesis Works in Plants

## Overview
Photosynthesis is the process plants use to turn light energy into chemical energy stored in sugar.
It takes place mainly in the leaves, inside organelles called chloroplasts, which contain the green
pigment chlorophyll.

## The two stages
1. **Light-dependent reactions** happen in the thylakoid membranes. Chlorophyll absorbs light, water
   molecules are split, oxygen is released as a by-product, and the energy carriers ATP and NADPH are made.
2. **The Calvin cycle** (light-independent reactions) happens in the stroma. The enzyme RuBisCO fixes
   carbon dioxide from the air, and ATP and NADPH are used to build glucose.

## Overall equation
6CO2 + 6H2O + light energy -> C6H12O6 + 6O2

## Why it matters
Photosynthesis produces the oxygen most living things breathe and is the starting point of almost
every food chain on Earth.
"""

OFF_TOPIC = """# How Volcanoes Form

## Overview
Volcanoes form where molten rock, called magma, rises through the Earth's crust. Most are found at
the boundaries of tectonic plates.

## Types
Shield volcanoes, like those in Hawaii, have gentle slopes made by runny lava. Stratovolcanoes, like
Mount Fuji, are steep and built from layers of ash and thick lava.

## Why it matters
Eruptions can be dangerous, but volcanic soil is very fertile and supports farming in many regions.
"""

WRONG_FACTS = """# How Photosynthesis Works in Plants

## Overview
Photosynthesis takes place in the mitochondria of root cells, where plants absorb oxygen from the
soil and release carbon dioxide into the air.

## The process
Plants mainly use moonlight, which is absorbed by a red pigment called hemoglobin. The energy is
stored as nitrogen gas, which the plant later burns to grow.

## Overall equation
6O2 + nitrogen -> 6CO2 + salt

## Why it matters
Photosynthesis is the main reason the oceans are salty.
"""

JUMBLED = """photosynthesis chloroplast yes light the and water split oxygen out ATP NADPH also
CALVIN cycle rubisco carbon dioxide glucose stroma thylakoid stage two stage one chlorophyll green
equation 6CO2 6H2O C6H12O6 6O2 food chain oxygen breathe leaves important sugar energy chemical
light energy stored plants process the a an of in it is was"""

CASES = {"good": GOOD, "off_topic": OFF_TOPIC, "wrong_facts": WRONG_FACTS, "jumbled": JUMBLED}


def fake_llms():
    """Two fake judges, to prove this checker can tell real from made-up scores."""
    def honest(prompt):
        report = prompt.split("REPORT:", 1)[1]
        rel = 2 if "Volcano" in report else 9
        acc = 2 if "mitochondria of root" in report else 8
        cla = 2 if "##" not in report else 9
        return json.dumps({"relevance": rel, "accuracy": acc, "clarity": cla, "comment": "fake honest judge"})

    def constant(prompt):
        return '{"relevance": 9, "accuracy": 9, "clarity": 9, "comment": "looks great"}'

    return honest, constant


def scan_for_made_up_data():
    """Find numbers typed into the code that are shown to users as if they were measured."""
    findings = []
    for path in (ROOT / "ui").rglob("*.js"):
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if re.search(r"\boverall\s*:\s*\d", line):
                findings.append(f"{path.relative_to(ROOT)}:{i}  hardcoded judge score")
    services = ROOT / "admin_backend" / "services"
    if services.exists():
        for path in services.glob("*.py"):
            for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if re.match(r"_seed_default_\w+\(", line):
                    findings.append(f"{path.relative_to(ROOT)}:{i}  fills the dashboard with sample data at startup ({line.split('(')[0]})")
    api = ROOT / "api" / "main.py"
    if api.exists():
        for i, line in enumerate(api.read_text(errors="ignore").splitlines(), 1):
            if re.search(r"duration_ms=\d+(\.\d+)?,", line):
                findings.append(f"api/main.py:{i}  fixed agent step time, not measured ({line.strip()})")
    return findings


def run_checks(llm=None, label="real LLM"):
    from evaluation import judge

    log_path = Path(tempfile.mkdtemp()) / "scores.jsonl"
    judge.LOG_PATH = str(log_path)

    print(f"\n=== Checking judge scores ({label}) ===")
    scores = {name: judge.grade_report(TOPIC, text, llm=llm) for name, text in CASES.items()}
    repeats = [scores["good"]] + [judge.grade_report(TOPIC, GOOD, llm=llm) for _ in range(2)]

    print(f"\n{'report':<12} {'rel':>4} {'acc':>4} {'cla':>4} {'overall':>8}  comment")
    for name, s in scores.items():
        if "error" in s:
            print(f"{name:<12} ERROR: {s['error']}")
        else:
            print(f"{name:<12} {s['relevance']:>4} {s['accuracy']:>4} {s['clarity']:>4} {s['overall']:>8}  {s['comment'][:60]}")

    if any("error" in s for s in list(scores.values()) + repeats):
        print("\nRESULT: could not grade every report (see errors above). Fix the LLM connection and rerun.")
        return False

    g = scores["good"]
    checks = [
        ("good report scores highest overall",
         all(g["overall"] >= scores[k]["overall"] + 1.5 for k in ("off_topic", "wrong_facts", "jumbled"))),
        ("off-topic report gets low relevance (<=4)", scores["off_topic"]["relevance"] <= 4),
        ("wrong-facts report gets low accuracy (<=4)", scores["wrong_facts"]["accuracy"] <= 4),
        ("jumbled report gets low clarity (<=4)", scores["jumbled"]["clarity"] <= 4),
        ("same report graded 3x stays within 1.5 points",
         max(r["overall"] for r in repeats) - min(r["overall"] for r in repeats) <= 1.5),
        ("scores are not all the same number",
         len({s["overall"] for s in scores.values()}) >= 2),
    ]
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    checks.append(("every score is logged with the judge's raw reply",
                   len(entries) == len(CASES) + 2 and all(e.get("raw_judge_output") for e in entries)))

    print()
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n  repeat scores for the good report: {[r['overall'] for r in repeats]}")
    print(f"  raw judge replies saved to: {log_path}")

    passed = all(ok for _, ok in checks)
    print("\nRESULT: " + ("scores behave like REAL judgements" if passed
                          else "scores do NOT behave like real judgements, look at the FAIL lines"))
    return passed


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--fake", action="store_true", help="offline self-test with fake judges")
    args = p.parse_args(argv)

    if args.fake:
        honest, constant = fake_llms()
        ok_honest = run_checks(honest, "fake HONEST judge, should PASS")
        ok_constant = run_checks(constant, "fake CONSTANT judge (made-up 9s), should FAIL")
        verdict = ok_honest and not ok_constant
        print("\n=== Self-test: " + ("checker works ✔" if verdict else "checker is broken ✘") + " ===")
        code = 0 if verdict else 1
    else:
        code = 0 if run_checks() else 1

    hits = scan_for_made_up_data()
    print("\n=== Made-up data check (UI + admin dashboard) ===")
    if hits:
        print("  WARNING: these values are typed into the code, not measured or judged:")
        for h in hits:
            print(f"    {h}")
    else:
        print("  OK: no hardcoded scores or sample data found")
    sys.exit(code)


if __name__ == "__main__":
    main()
