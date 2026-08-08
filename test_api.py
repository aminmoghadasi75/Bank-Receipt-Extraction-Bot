"""
Simple test script to verify Google Gemini API Key is working.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

print(f"🔑 API Key found: {'Yes' if API_KEY else 'No'}")
print(f"📦 API Key (first 10 chars): {API_KEY[:10]}..." if API_KEY else "❌ No API Key found!")
print(f"🤖 Model: {MODEL}")
print("-" * 50)

if not API_KEY:
    print("❌ ERROR: No GEMINI_API_KEY found in .env file!")
    exit(1)

try:
    from google import genai
    from google.genai import types

    # Initialize client
    client = genai.Client(api_key=API_KEY)

    print("📤 Sending test question to Gemini...")
    print("Question: 'Where is the capital of Iran? Answer in one word.'")
    print("-" * 50)

    # Simple test query
    response = client.models.generate_content(
        model=MODEL,
        contents="What is 2 + 8? Answer in one word."
    )

    print(f"✅ SUCCESS! API is working!")
    print(f"📥 Response: {response.text}")

except ImportError:
    print("❌ ERROR: google-genai package is not installed.")
    print("   Run: pip install google-genai")

except Exception as e:
    print(f"❌ ERROR: API call failed!")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {str(e)}")
    
    # Provide helpful hints based on common errors
    err_str = str(e).lower()
    if "api_key" in err_str or "api key" in err_str or "invalid" in err_str:
        print("\n💡 Hint: Your API Key seems to be invalid or expired.")
        print("   Get a new key at: https://aistudio.google.com/apikey")
    elif "quota" in err_str or "rate" in err_str:
        print("\n💡 Hint: You may have exceeded your API quota/rate limit.")
    elif "model" in err_str or "not_found" in err_str or "404" in err_str:
        print(f"\n💡 Hint: Model '{MODEL}' might be retired or unavailable.")
        print("   Try active models: gemini-2.5-flash or gemini-2.5-pro")
    elif "network" in err_str or "connect" in err_str or "timeout" in err_str:
        print("\n💡 Hint: Network connection issue. Check your internet connection.")

