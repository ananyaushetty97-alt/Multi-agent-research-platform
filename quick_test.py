import requests

URL = "http://localhost:8000/generate"


def ask(topic, session_id=None):
    body = {"topic": topic}
    if session_id:
        body["session_id"] = session_id
    r = requests.post(URL, json=body, timeout=900)
    if r.status_code != 200:
        print("ERROR", r.status_code, r.text)
        raise SystemExit(1)
    return r.json()


print("=== 1. New research ===")
r1 = ask("Impact of renewable energy on grid stability")
sid = r1["session_id"]
print("intent:", r1["intent"], "| cached:", r1["cached"], "| seconds:", r1["seconds"])
print("sources:", [s["url"] for s in r1["sources"][:3]])
print("has [1]:", "[1]" in r1["report"], "| length:", len(r1["report"]))

print("\n=== 2. Modify, same session (expect intent: modify) ===")
r2 = ask("make it half as long", sid)
print("intent:", r2["intent"], "| length:", len(r1["report"]), "->", len(r2["report"]))
print("still cites:", "[1]" in r2["report"], "| sources:", len(r2["sources"]))

print("\n=== 3. Question, same session (expect intent: question, score: None) ===")
r3 = ask("what does grid stability mean?", sid)
print("intent:", r3["intent"], "| score:", r3["score"])
print(r3["report"][:300])

print("\n=== 4. Modify again AFTER the question (should edit the report, not the answer) ===")
r4 = ask("add a short conclusion", sid)
print("intent:", r4["intent"], "| length:", len(r4["report"]))

print("\n=== 5. Fresh session, same topic as call 1 (expect cached: True) ===")
r5 = ask("Impact of renewable energy on grid stability")
print("cached:", r5["cached"], "| sources:", len(r5["sources"]), "| seconds:", r5["seconds"])