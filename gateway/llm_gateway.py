import os
from groq import Groq
from ollama import Client as OllamaClient
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
ollama_client = OllamaClient(host="http://localhost:11434")

GROQ_MODEL = "qwen/qwen3.8-27b"      # check console.groq.com/docs/models — Groq renames/deprecates models occasionally
OLLAMA_MODEL = "qwen2.5:7b"          # must match what you pulled with `ollama pull`


def _call_groq(prompt: str, system_prompt: str) -> str:
    lower_p = prompt.lower()
    lower_s = system_prompt.lower()
    # Dynamic token budgeting to respect Groq OTPM limits (1000 OTPM on free tier)
    if "one word" in lower_p or "exactly the word" in lower_p or "classifier" in lower_s:
        actual_max = 30
    elif "fact-checker" in lower_s or "verified" in lower_p:
        actual_max = 150
    elif "summariz" in lower_s or "summarizer" in lower_s:
        actual_max = 350
    elif "judge" in lower_s or "grade" in lower_s:
        actual_max = 200
    else:
        actual_max = 500

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=actual_max,
    )
    return response.choices[0].message.content


def _call_ollama(prompt: str, system_prompt: str) -> str:
    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )
    return response["message"]["content"]


def call_llm(prompt: str, system_prompt: str = "You are a helpful research assistant.") -> str:
    """
    Every agent calls this. Tries Groq (Qwen, cloud, fast) first.
    Falls back to Ollama (Qwen, local) if Groq fails for any reason
    (rate limit, network issue, outage, bad API key, etc).
    """
    try:
        return _call_groq(prompt, system_prompt)
    except Exception as e:
        print(f"[gateway] Groq call failed ({e}), falling back to Ollama...")
        try:
            return _call_ollama(prompt, system_prompt)
        except Exception as e2:
            raise RuntimeError(f"Both Groq and Ollama failed. Groq error: {e}. Ollama error: {e2}")