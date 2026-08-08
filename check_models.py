import google.generativeai as genai
from config.settings import GEMINI_API_KEY

def main():
    print(f"Testing API key: {GEMINI_API_KEY[:10]}...")
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        models = genai.list_models()
        print("Available models:")
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                print(f" - {m.name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
