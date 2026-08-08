"""
Simple test script to verify Google Gemini API Key is working.
"""

import os
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

print(f"🔑 API Key found: {'Yes' if API_KEY else 'No'}")
print(f"📦 API Key (first 10 chars): {API_KEY[:10]}..." if API_KEY else "❌ No API Key found!")
print(f"🤖 Model: {MODEL}")
print("-" * 50)

if not API_KEY or API_KEY.startswith("AIzaSy_YOUR_ACTUAL"):
    print("❌ ERROR: Please put a valid GEMINI_API_KEY in your .env file!")
    print("   Get a key from: https://aistudio.google.com/apikey")
    exit(1)

try:
    import google.generativeai as genai

    # پیکربندی API
    genai.configure(api_key=API_KEY)

    # ساخت نمونه مدل
    model = genai.GenerativeModel(MODEL)
    ask_model= "What is the capital of Germany? Answer in one word."

    print("📤 Sending test question to Gemini...")
    print("Question: "+ask_model)
    print("-" * 50)

    # ارسال درخواست به API
    response = model.generate_content(ask_model)

    print(f"✅ SUCCESS! API is working!")
    print(f"📥 Response: {response.text}")

except ImportError:
    print("❌ ERROR: Required packages are not installed.")
    print("   Please run: pip install google-generativeai python-dotenv")

except Exception as e:
    print(f"❌ ERROR: API call failed!")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error message: {str(e)}")
    
    err_str = str(e).lower()
    if "api_key" in err_str or "invalid" in err_str or "403" in err_str:
        print("\n💡 Hint: Your API Key seems to be invalid or expired.")
        print("   Get a new key at: https://aistudio.google.com/apikey")
    elif "model" in err_str or "not_found" in err_str or "404" in err_str:
        print(f"\n💡 Hint: Model '{MODEL}' is retired or unavailable.")
        print("   Use active model: gemini-3.6-flash")
    elif "network" in err_str or "connect" in err_str or "timeout" in err_str:
        print("\n💡 Hint: Network connection issue. Check your internet connection or Proxy/VPN.")