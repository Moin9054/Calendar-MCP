# llm.py
# Uses OpenRouter (Llama-8B) by default.
# You enter your API key in PowerShell each session:
#   $env:OPENROUTER_API_KEY = "sk-your_api_key_here"
#
# If no key is set or any network error occurs, falls back to mock LLM.

import os
import requests
import json

# Hardcoded correct OpenRouter endpoint
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

def generate(prompt: str, max_tokens: int = 256) -> str:
    """
    Calls OpenRouter API if API key exists.
    Falls back to a mock LLM response if key missing or call fails.
    """
    if not OPENROUTER_KEY:
        snippet = prompt[:400].replace("\n", " ")
        return f"[MOCK LLM]\nBased on context: {snippet}\n\nReply: (mock) I scheduled your meeting successfully."

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json",
        # Optional but recommended header
        "HTTP-Referer": "https://openrouter.ai", 
        "X-Title": "Calendar MCP Demo"
    }

    payload = {
        "model": "meta-llama/llama-3-8b-instruct", 
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "choices" in data and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"].strip()
            elif "text" in choice:
                return choice["text"].strip()

        return json.dumps(data, indent=2)[:1000]

    except requests.exceptions.RequestException as e:
        print("⚠️  Network or API error:", e)
        snippet = prompt[:400].replace("\n", " ")
        return f"[MOCK LLM - fallback]\nBased on context: {snippet}\n\nReply: (mock fallback) Meeting scheduled."

