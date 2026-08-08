"""
Quick diagnostic: test all keys from GEMINI_API_KEYS with generateContent 
to identify which are working (200), rate-limited (429), or forbidden (403).
"""
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

raw_keys = os.getenv("GEMINI_API_KEYS", "")
keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

print(f"Testing {len(keys)} API key(s) with model '{model}'...\n")
print(f"{'#':<4} {'Key':<25} {'Status':<8} {'Result'}")
print("-" * 70)

working_keys = []

for i, key in enumerate(keys, 1):
    masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else key
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
    
    try:
        res = httpx.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            txt = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"{i:<4} {masked:<25} {'200 ✅':<8} {txt}")
            working_keys.append(key)
        elif res.status_code == 429:
            print(f"{i:<4} {masked:<25} {'429 🔴':<8} Rate Limited / Quota Exceeded")
        elif res.status_code == 403:
            print(f"{i:<4} {masked:<25} {'403 🚫':<8} Permission Denied")
        else:
            err = res.json().get("error", {}).get("message", res.text[:60])
            print(f"{i:<4} {masked:<25} {str(res.status_code)+' ⚠️ ':<8} {err}")
    except Exception as e:
        print(f"{i:<4} {masked:<25} {'ERR ❌':<8} {str(e)[:60]}")
    
    time.sleep(1)

print(f"\n{'='*70}")
print(f"✅ Working keys: {len(working_keys)} / {len(keys)}")
if working_keys:
    print(f"\nCopy these working keys into .env as GEMINI_API_KEYS:")
    print(",".join(working_keys))
