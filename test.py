from dotenv import load_dotenv
import os
from tavily import TavilyClient
from groq import Groq

load_dotenv()

print("Testing Groq - Topic Research...")
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

res1 = groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role":"user","content":"Say exactly: Groq 70B is working!"}]
)
print(res1.choices[0].message.content)

print("\nTesting Groq - Blog Writing...")
res2 = groq_client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role":"user","content":"Say exactly: Blog writer is working!"}]
)
print(res2.choices[0].message.content)

print("\nTesting Tavily - Trend Search...")
t = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
s = t.search("VN editor templates 2026", max_results=1)
print("Tavily found:", s["results"][0]["title"])

print("\nAll working! Phase 1 complete. Ready for Phase 2.")
