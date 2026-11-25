import sys
sys.path.insert(0, ".")
import os
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

print("--- 1. Testing Groq Candidate & Fallback Model IDs ---")
candidate_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "allam-2-7b"]

for model_id in candidate_models:
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a concise research AI."},
                {"role": "user", "content": "Reply with exactly 3 words: Artificial Intelligence rocks."}
            ],
            max_tokens=25,
            temperature=0.2,
        )
        dur = round((time.perf_counter() - t0) * 1000, 1)
        choice = resp.choices[0].message
        content = choice.content or choice.reasoning or ""
        print(f"Model [{model_id}]: SUCCESS ({dur}ms) -> '{content.strip()[:60]}'")
    except Exception as e:
        dur = round((time.perf_counter() - t0) * 1000, 1)
        print(f"Model [{model_id}]: FAILED ({dur}ms) -> {e}")

print("\n--- 2. Verifying Gateway Logging & Model Tracking ---")
import logging
from gateway.llm_gateway import call_llm, start_llm_request_session, get_llm_request_telemetry

# Set logger to print
logging.basicConfig(level=logging.INFO)
start_llm_request_session()

res = call_llm("Summarize quantum computing in one sentence.", system_prompt="You are a physics expert.", max_tokens=60)
print(f"call_llm output: {res[:100]}...")

telem = get_llm_request_telemetry()
print(f"Telemetry actual_model: {telem['actual_model']}")
print(f"Telemetry fallback_used: {telem['fallback_used']}")
print(f"Telemetry tokens: total={telem['total_tokens']}, cost=${telem['estimated_cost_usd']}")
assert telem['actual_model'] in candidate_models
assert telem['total_tokens'] > 0

print("\n--- 3. Testing Rate-Limit Error Handling (Clear Message, No Hang) ---")
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# Simulate rate limit on all models in pipeline
with patch("api.main.parts.check_cache", return_value=None), \
     patch("api.main.parts.run_pipeline", side_effect=RuntimeError("Both Groq and Ollama failed. Groq error: Error code: 429 - {'error': {'message': 'Rate limit reached for requests per minute (TPM)'}}. Ollama error: Connection refused")):
    t_start = time.perf_counter()
    resp = client.post("/generate", json={"topic": "Uncached topic test for rate limit"})
    elapsed = round((time.perf_counter() - t_start) * 1000, 2)
    print(f"Simulated rate limit response status: {resp.status_code} in {elapsed}ms")
    print(f"Response body: {resp.json()}")
    assert resp.status_code == 429
    assert "rate-limited" in resp.json()["detail"].lower()
    assert elapsed < 5000, "Response must return within milliseconds without hanging!"

print("\nSTEP 3 VERIFIED SUCCESSFULLY!")
