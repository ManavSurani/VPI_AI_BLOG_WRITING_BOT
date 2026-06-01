from dotenv import load_dotenv
from google import genai
from key_manager import KeyManager

load_dotenv()

print("Testing Gemini with KeyManager...\n")
try:
    gemini_km = KeyManager("GEMINI_API_KEY")
    client = genai.Client(api_key=gemini_km.current_key())
    
    r = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say exactly: Gemini is working with KeyManager!"
    )
    text = r.text if r.text else ""
    print(f"\n[SUCCESS] {text.strip()}")
except Exception as e:
    print(f"\n[ERROR] {e}")
