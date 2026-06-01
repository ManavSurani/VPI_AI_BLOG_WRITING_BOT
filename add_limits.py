import os
import re

with open('main.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add GLOBAL TRACKERS at the top
if 'API_USAGE = {' not in text:
    text = text.replace('supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])', 
'''supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# Usage Trackers
API_USAGE = {
    "groq_tokens": 0,
    "tavily_searches": 0,
    "supabase_posts": 0
}''')

# 2. Update groq() to track tokens
groq_replacement = '''def groq(prompt, model="llama-3.3-70b-versatile", tokens=4500):
    global API_USAGE
    try:
        r = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=tokens
        )
        if hasattr(r, 'usage') and r.usage:
            API_USAGE["groq_tokens"] += r.usage.total_tokens
        return r.choices[0].message.content
    except Exception as e:
        if "429" in str(e) or "rate limit" in str(e).lower():
            print(f"  [!] Rate limit reached for {model}. Falling back to llama-3.1-8b-instant with reduced tokens...")
            try:
                safe_tokens = min(tokens, 3000)
                r = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=safe_tokens
                )
                if hasattr(r, 'usage') and r.usage:
                    API_USAGE["groq_tokens"] += r.usage.total_tokens
                return r.choices[0].message.content
            except Exception as e2:
                if "413" in str(e2):
                    print(f"  [!] Fallback model hit TPM limit. Attempting with 1500 max_tokens...")
                    try:
                        r = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=1500
                        )
                        if hasattr(r, 'usage') and r.usage:
                            API_USAGE["groq_tokens"] += r.usage.total_tokens
                        return r.choices[0].message.content
                    except Exception as e3:
                        print(f"  [!] Final fallback failed: {e3}")
                        raise e3
                print(f"  [!] Fallback model also failed: {e2}")
                raise e2
        raise e
'''

text = re.sub(r'def groq\(prompt, model="llama-3\.3-70b-versatile", tokens=4500\):.*?        raise e\n', groq_replacement, text, flags=re.DOTALL)

# 3. Track Tavily searches in main.py
if 'API_USAGE["tavily_searches"] += 1' not in text:
    text = text.replace('results = tavily.search(query, max_results=3)', 'API_USAGE["tavily_searches"] += 1\n            results = tavily.search(query, max_results=3)')

# 4. Grab supabase total posts in decide_topic
if 'API_USAGE["supabase_posts"] = len(published_titles)' not in text:
    text = text.replace('published_titles = [p["title"] for p in existing.data if isinstance(p, dict)]', 
'''published_titles = [p["title"] for p in existing.data if isinstance(p, dict)]
    API_USAGE["supabase_posts"] = len(published_titles)''')


# 5. Add Print Output
print_table = '''
            print(f"\\n⚙️  API LIMIT & RESOURCE USAGE:")
            print(f"  | Issue           | Problem                                             | Solution                                      |")
            print(f"  |-----------------|-----------------------------------------------------|-----------------------------------------------|")
            
            model_info = "8B model output" if API_USAGE['groq_tokens'] < 8000 else "70B model output"
            if word_count < 1500:
                print(f"  | {model_info:<15} | {API_USAGE['groq_tokens']:<5} tokens < {word_count} words blog                     | Use 70B for full blog, or split into sections |")
            else:
                print(f"  | {model_info:<15} | {API_USAGE['groq_tokens']:<5} tokens = {word_count} words blog                     | Good length, model choice works               |")
                
            print(f"  | Supabase Free   | {API_USAGE['supabase_posts']:<4} posts in DB = ~50,000 limit (at 10KB each)   | Upgrade to Pro if storing 10K+ posts          |")
            
            # site_crawler = ~6 calls, fact_verifier = ~6 calls
            total_tavily = API_USAGE['tavily_searches'] + 12 
            print(f"  | Tavily Free     | {total_tavily:<4} searches/month = 33/day                       | Good for <10 blogs/day research               |")
            print(f"  | Groq Daily      | ~10K tokens/day (free tier)                         | Need paid API key for production              |")
            print(f"  |-----------------|-----------------------------------------------------|-----------------------------------------------|")
            
            print("\\n" + "+" + "="*48 + "+")'''

if 'API LIMIT & RESOURCE USAGE' not in text:
    text = text.replace('print("\\n" + "+" + "="*48 + "+")\n            print("|  ✨ PREMIUM CONTENT READY ✨                |")', print_table + '\n            print("|  ✨ PREMIUM CONTENT READY ✨                |")')


with open('main.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated main.py with limits")
