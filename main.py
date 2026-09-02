"""
main.py — VN Code Pro Blog Bot v7
Gemini 2.5 Flash → blog writing, fact-check, metadata
Groq Llama 70B   → trend extraction, topic research, quality check
"""

from dotenv import load_dotenv
import os, json, re, time
import requests
import math
from tavily import TavilyClient
from google import genai
from groq import Groq
from supabase import create_client
from datetime import datetime, timezone
from typing import Any
import sys, codecs
import site_crawler
import fact_verifier
from key_manager import KeyManager

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "replace")

load_dotenv()

gemini_km    = KeyManager("GEMINI_API_KEY")
groq_km      = KeyManager("GROQ_API_KEY")
genai_client = genai.Client(api_key=gemini_km.current_key())
groq_client  = Groq(api_key=groq_km.current_key())
tavily       = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
supabase     = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

API_USAGE = {
    "gemini_calls": 0,
    "gemini_tokens": 0,
    "groq_calls": 0,
    "groq_tokens": 0,
    "tavily_searches": 0,
    "supabase_posts": 0
}

# ─── Gemini per-call retry counters (module-level to satisfy Pyright) ────────
_gemini_tpm_retries: int = 0
_gemini_503_retries: int = 0


def log_error(location: str, details: str):
    try:
        now = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        with open("bot_errors.txt", "a", encoding="utf-8") as f:
            f.write(f"[{now}]\n")
            f.write(f"Location: {location}\n")
            f.write(f"Error:    {details}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"  [!] Failed to write to error log: {e}")


# ─── GEMINI HELPER (blog writing, fact-check, metadata) ──────────
def gemini_call(prompt, json_mode=False, max_retries=3):
    global genai_client, API_USAGE, _gemini_tpm_retries, _gemini_503_retries
    API_USAGE["gemini_calls"] += 1
    delay          = 5
    total_attempts = max_retries * max(len(gemini_km.keys), 1)

    for attempt in range(total_attempts):
        try:
            config = genai.types.GenerateContentConfig(
                response_mime_type="application/json" if json_mode else "text/plain"
            )
            r = genai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=config
            )
            if r.usage_metadata and r.usage_metadata.total_token_count:
                API_USAGE["gemini_tokens"] += r.usage_metadata.total_token_count

            # Reset all counters on success
            _gemini_tpm_retries = 0
            _gemini_503_retries = 0
            return r.text

        except Exception as e:
            err = str(e)

            # ── ERROR TYPE 1: Invalid key (401/403) ──────────────────────
            # Wrong key, deleted key, no permission
            # Action: Mark key as permanently bad, rotate immediately
            if any(x in err for x in ["401", "403", "API_KEY_INVALID"]) or \
               ("invalid" in err.lower() and "key" in err.lower()):
                print(f"  [!] Gemini Key {gemini_km.idx+1} is invalid (401/403)")
                print(f"  Marking as permanently bad and rotating...")
                _gemini_tpm_retries = 0
                _gemini_503_retries = 0
                new_key      = gemini_km.rotate(reason="invalid")
                genai_client = genai.Client(api_key=new_key)
                continue  # retry immediately with new key

            # ── ERROR TYPE 2: Google Server Down (503) ───────────────────
            # Google servers temporarily overloaded or unavailable
            # Nothing wrong with your key — just wait and retry same key
            elif "503" in err or "UNAVAILABLE" in err or \
                 "unavailable" in err.lower() or "server error" in err.lower():

                _gemini_503_retries += 1

                if _gemini_503_retries == 1:
                    # First 503 — short wait, usually resolves in seconds
                    print(f"  [!] Google server hiccup (503) — attempt 1")
                    print(f"  Waiting 30 seconds for Google servers to recover...")
                    time.sleep(30)
                    continue  # retry SAME key — not a key problem

                elif _gemini_503_retries == 2:
                    # Second 503 — servers still struggling, wait longer
                    print(f"  [!] Google server still down (503) — attempt 2")
                    print(f"  Waiting 60 seconds...")
                    time.sleep(60)
                    continue  # retry SAME key

                elif _gemini_503_retries == 3:
                    # Third 503 — try different key in case regional issue
                    print(f"  [!] Google server down after 2 attempts — attempt 3")
                    print(f"  Trying different key in case of regional issue...")
                    _gemini_503_retries = 0
                    new_key      = gemini_km.rotate(reason="rate_limit")
                    genai_client = genai.Client(api_key=new_key)
                    continue

                else:
                    # Google having major outage — stop and inform user
                    _gemini_503_retries = 0
                    msg = (
                        "\n  Google Gemini servers are unavailable (503) after 3 attempts.\n"
                        "  This is Google's problem, not yours.\n"
                        "  Check: https://status.cloud.google.com\n"
                        "  Try again in 10-15 minutes."
                    )
                    log_error("Gemini API (503)", msg)
                    raise RuntimeError(msg)

            # ── ERROR TYPE 3: TPM Spike (429 per minute) ─────────────────
            # Too many tokens sent per minute — NOT daily quota
            # Resets every 60 seconds — wait and retry same key
            elif any(x in err for x in ["429", "quota", "exhausted", "RESOURCE_EXHAUSTED"]) and \
                 ("per_minute" in err.lower() or "minute" in err.lower() or
                  "GenerateContentInputTokensPerModelPerMinute" in err):

                _gemini_tpm_retries += 1

                if _gemini_tpm_retries == 1:
                    # First TPM hit — wait 65 sec (60 sec reset + 5 buffer)
                    print(f"  [!] Gemini TPM limit hit (per-minute spike) — attempt 1")
                    print(f"  Waiting 65 seconds for TPM to reset...")
                    print(f"  (This is NOT your daily quota — key is still valid)")
                    time.sleep(65)
                    continue  # retry SAME key

                elif _gemini_tpm_retries == 2:
                    # Second TPM hit — Google slow to reset, wait double
                    print(f"  [!] TPM still not reset — attempt 2")
                    print(f"  Waiting 120 seconds...")
                    time.sleep(120)
                    continue  # retry SAME key

                elif _gemini_tpm_retries == 3:
                    # Third TPM hit — rotate as last resort
                    print(f"  [!] TPM persisting after 3 attempts — rotating key...")
                    _gemini_tpm_retries = 0
                    new_key      = gemini_km.rotate(reason="rate_limit")
                    genai_client = genai.Client(api_key=new_key)
                    continue

                else:
                    # Cannot resolve TPM — stop
                    _gemini_tpm_retries = 0
                    msg = (
                        "\n  Gemini TPM limit could not be resolved after 3 attempts.\n"
                        "  Try again in a few minutes.\n"
                        "  Tip: Add sleep between heavy Gemini calls."
                    )
                    log_error("Gemini API (TPM)", msg)
                    raise RuntimeError(msg)

            # ── ERROR TYPE 4: Daily Quota Exhausted (429 daily) ──────────
            # Real daily limit used up — key cannot be used until tomorrow
            # Action: Rotate to next key immediately
            elif any(x in err for x in ["429", "quota", "exhausted", "RESOURCE_EXHAUSTED"]) or \
                 "quota" in err.lower():
                print(f"  [!] Gemini Key {gemini_km.idx+1} daily quota exhausted")
                print(f"  Rotating to next key...")
                _gemini_tpm_retries = 0
                _gemini_503_retries = 0
                new_key      = gemini_km.rotate(reason="rate_limit")
                genai_client = genai.Client(api_key=new_key)
                continue  # retry immediately with new key

            # ── ERROR TYPE 5: Unknown Error ───────────────────────────────
            # Anything else — wait and retry up to max_retries times
            else:
                _gemini_tpm_retries = 0
                _gemini_503_retries = 0
                print(f"  [!] Gemini unknown error (attempt {attempt+1}): {err[:80]}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    delay *= 2  # exponential backoff: 5s, 10s, 20s
                else:
                    log_error("Gemini API", f"Failed after {max_retries} retries. Last error: {err}")
                    raise e

    return ""


# ─── GROQ HELPER (trend research, topic picking, quality check) ───
def groq_call(prompt, json_mode=False, max_retries=3):
    global groq_client, API_USAGE
    API_USAGE["groq_calls"] += 1
    total_attempts = max_retries * max(len(groq_km.keys), 1)

    for attempt in range(total_attempts):
        try:
            if json_mode:
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
            else:
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000
                )
            if hasattr(r, "usage") and r.usage:
                API_USAGE["groq_tokens"] += r.usage.total_tokens
            return r.choices[0].message.content

        except Exception as e:
            err = str(e)

            # Invalid key
            if any(x in err for x in ["401", "403", "invalid_api_key"]) or \
               "invalid" in err.lower() and "key" in err.lower():
                new_key     = groq_km.rotate(reason="invalid")
                groq_client = Groq(api_key=new_key)
                continue

            # Rate limit
            elif "429" in err or "rate" in err.lower() or "limit" in err.lower():
                new_key     = groq_km.rotate(reason="rate_limit")
                groq_client = Groq(api_key=new_key)
                continue

            # Other error — fallback to smaller model
            else:
                print(f"  [!] Groq error (attempt {attempt+1}): {err[:80]}")
                try:
                    r = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1500
                    )
                    if hasattr(r, "usage") and r.usage:
                        API_USAGE["groq_tokens"] += r.usage.total_tokens
                    return r.choices[0].message.content
                except Exception as e2:
                    if attempt >= max_retries - 1:
                        log_error("Groq API", f"Failed after {max_retries} attempts. Last error: {str(e2)}")
                        raise e2
    return ""


def parse_json(raw) -> Any:
    if not raw:
        return {}
    clean = re.sub(r"```json|```", "", raw).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    try:
        return json.loads(match.group() if match else clean)
    except Exception:
        return {}


# ─── STEP 1: Trend Research — GROQ extracts signals ──────────────
def research_trends():
    print("Step 1: Researching what's trending right now...")

    searches = [
        "trending VN Editor templates viral Instagram Reels India 2026",
        "trending Instagram Reels editing styles transitions India 2026",
        "viral song reel template India Instagram trending 2026"
    ]

    raw_results = []
    for query in searches:
        try:
            API_USAGE["tavily_searches"] += 1
            res = tavily.search(query, max_results=4)
            if res and "results" in res:
                for r in res["results"]:
                    content = r.get("content", "")
                    if content:
                        raw_results.append({
                            "title": r.get("title", ""),
                            "content": content[:500]
                        })
        except Exception as e:
            print(f"  Warning: Search failed — {query[:40]}...")
            continue

    if not raw_results:
        print("  Warning: No results — using fallback trends")
        return {
            "trending_styles": ["cinematic", "beat-sync", "double exposure", "transformation", "aesthetic"],
            "trending_reel_formats": ["2-side reels", "transition reels", "song-based reels"],
            "trending_occasions": ["wedding", "festival", "couple", "birthday"],
            "hot_keywords": ["viral reels 2026", "VN templates", "cinematic edit"],
            "summary": "Beat-sync and cinematic styles are trending for Indian creators in 2026."
        }

    # GROQ extracts structured signals — fast reasoning task
    prompt = f"""Analyze these search results about trending VN Editor templates and Instagram Reels in India 2026.

Search data:
{chr(10).join(f'Title: {r["title"]} | Content: {r["content"]}' for r in raw_results[:10])}

Extract real trending signals. Return ONLY valid JSON:
{{
  "trending_styles": ["style1", "style2", "style3", "style4", "style5"],
  "trending_reel_formats": ["format1", "format2", "format3"],
  "trending_occasions": ["occasion1", "occasion2", "occasion3"],
  "hot_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "summary": "2 sentence summary of what is trending right now for Indian creators"
}}"""

    raw = groq_call(prompt, json_mode=True)
    trends = parse_json(raw)

    if trends:
        print(f"  Trending styles:  {', '.join(trends.get('trending_styles', [])[:3])}")
        print(f"  Trending formats: {', '.join(trends.get('trending_reel_formats', [])[:3])}")
        print(f"  Summary: {trends.get('summary', '')[:80]}")
    else:
        print(f"  Gathered {len(raw_results)} raw signals")

    return trends or {"raw": [r["content"] for r in raw_results]}


# ─── STEP 2: Pick Unique Topic — GROQ reasons fast ───────────────
def decide_topic(trends, site_knowledge, verified_facts):
    print("Step 2: Deciding unique blog topic...")

    existing = supabase.table("blog_posts").select("title").execute()
    published_titles = []
    if existing.data:
        published_titles = [p["title"] for p in existing.data if isinstance(p, dict)]
    API_USAGE["supabase_posts"] = len(published_titles)

    if "pages" in site_knowledge and "blogs" in site_knowledge["pages"]:
        published_titles += site_knowledge["pages"]["blogs"].get("published_titles", [])

    categories = site_knowledge["pages"]["templates"].get("categories", [])

    trend_text = (
        f"Trending styles: {', '.join(trends.get('trending_styles', []))}\n"
        f"Trending formats: {', '.join(trends.get('trending_reel_formats', []))}\n"
        f"Trending occasions: {', '.join(trends.get('trending_occasions', []))}\n"
        f"Hot keywords: {', '.join(trends.get('hot_keywords', []))}\n"
        f"Summary: {trends.get('summary', '')}"
    ) if isinstance(trends, dict) else "\n".join(f"- {t}" for t in trends[:9])

    prompt = f"""You are an SEO strategist for VN Code Pro (vncodepro.com) — Indian website selling VN Editor templates via QR code for Instagram Reels creators.

WHAT IS TRENDING RIGHT NOW:
{trend_text}

REAL TEMPLATE CATEGORIES ON VN CODE PRO:
{', '.join(categories)}

ALREADY PUBLISHED BLOGS (never repeat):
{chr(10).join(f'- {t}' for t in published_titles[:20]) if published_titles else '- None yet'}

Pick ONE completely fresh, specific blog topic:
1. Based on real trending signals
2. Matches a real VN Code Pro template category
3. Not covered in published blogs
4. Specific actionable title
5. Will rank on Google for Indian creators in 2026

GOOD titles:
- "How to Make Beat-Sync Wedding Reels with VN Templates in 2026"
- "5 Cinematic Transformation VN Templates Trending on Instagram India"
- "Festival Reels That Go Viral — VN Templates Guide 2026"

BAD titles (too generic):
- "Best Travel Templates 2026"
- "VN Editor Tips"

Return ONLY valid JSON:
{{
  "title": "specific actionable title",
  "keyword": "3-4 word seo phrase",
  "category": "which VN Code Pro category",
  "angle": "what makes this fresh and unique",
  "target_reader": "who specifically will search for this"
}}"""

    raw = groq_call(prompt, json_mode=True)
    data = parse_json(raw)

    for key in ["title", "keyword", "category", "angle", "target_reader"]:
        if key not in data:
            data[key] = ""

    print(f"  Topic:    {data.get('title', 'N/A')[:60]}")
    print(f"  Keyword:  {data.get('keyword', 'N/A')}")
    print(f"  Angle:    {data.get('angle', 'N/A')[:60]}")
    return data


# ─── STEP 3: Write Blog — GEMINI (best long-form writer) ─────────
def write_blog(topic, site_knowledge, verified_facts):
    print("Step 3: Writing blog with Gemini...")

    process_steps     = site_knowledge["pages"]["how_it_works"]["steps"]
    testimonials      = site_knowledge["pages"]["homepage"]["testimonials"]
    categories        = site_knowledge["pages"]["templates"]["categories"]
    safe_claims       = verified_facts.get("safe_claims", [])
    corrections       = verified_facts.get("corrections", {})

    prompt = f"""You are a professional blog writer for VN Code Pro (vncodepro.com).

BLOG DETAILS:
Title: {topic['title']}
Keyword: {topic['keyword']}
Category: {topic['category']}
Angle: {topic['angle']}
Target reader: {topic['target_reader']}

VERIFIED FACTS — ONLY use these claims. Do NOT invent statistics or fake data:
{json.dumps(safe_claims, indent=2)}

CRITICAL CORRECTIONS — MUST follow:
{json.dumps(corrections, indent=2)}

REAL INTERNAL LINKS — ONLY use these URLs:
- https://vncodepro.com/templates
- https://vncodepro.com/how-it-works
- https://vncodepro.com/about
- https://vncodepro.com/contact-us
- https://vncodepro.com/blogs
- https://vncodepro.com/refund-policy

REAL 6-STEP PROCESS (use exactly):
{json.dumps(process_steps, indent=2)}

REAL TESTIMONIALS (use these exact quotes — no names, just roles):
{json.dumps(testimonials, indent=2)}

REAL CATEGORIES: {', '.join(categories)}

WRITING STYLE:
- Short punchy sentences — max 15 words each
- Bullet points for lists, NOT long paragraphs
- Friendly tone like a helpful creator talking to another creator
- NO robotic phrases: "It is worth noting", "Firstly Secondly", "In conclusion"
- NO broken fragments: "And, time-consuming. You need help."
- NO excessive commas breaking sentences
- Smooth natural complete sentences
- Use variations of "{topic['keyword']}" to avoid keyword stuffing (max 4 exact matches)
- Mention "2026" at least 4 times naturally
- Mention "VN Code Pro" at least 12 times
- NO markdown links. Always use <a href="..."> HTML tags.
- NO markdown lists (* or -). Always use <ul> and <li> HTML tags.
- MINIMUM 1500 words

STRUCTURE (exact HTML tags):

<h1>{topic['title']}</h1>

<p>[Strong 2-3 sentence hook — relatable problem or surprising fact. Smooth natural sentences.]</p>

<h2>Why {topic['category']} Are Essential for Creators in 2026</h2>
<p>[2-3 sentences about the opportunity/trend]</p>
<ul>
<li>[specific reason]</li>
<li>[specific reason]</li>
<li>[specific reason]</li>
<li>[specific reason]</li>
<li>[specific reason]</li>
</ul>

<h2>What Makes VN Code Pro Different</h2>
<p>[2-3 sentences using only safe claims]</p>
<ul>
<li>[confirmed feature]</li>
<li>[confirmed feature]</li>
<li>[confirmed feature]</li>
<li>[confirmed feature]</li>
<li>[confirmed feature]</li>
</ul>

<h2>Best {topic['category']} Styles on VN Code Pro</h2>
<p>[1-2 sentence intro]</p>

<h3>[Editing Style Name 1]</h3>
<p>[2-3 smooth sentences]</p>
<ul><li>[feature]</li><li>[feature]</li><li>[feature]</li></ul>

<h3>[Editing Style Name 2]</h3>
<p>[description]</p>
<ul><li>[feature]</li><li>[feature]</li><li>[feature]</li></ul>

<h3>[Editing Style Name 3]</h3>
<p>[description]</p>
<ul><li>[feature]</li><li>[feature]</li><li>[feature]</li></ul>

<h3>[Editing Style Name 4]</h3>
<p>[description]</p>
<ul><li>[feature]</li><li>[feature]</li><li>[feature]</li></ul>

<h3>[Editing Style Name 5]</h3>
<p>[description]</p>
<ul><li>[feature]</li><li>[feature]</li><li>[feature]</li></ul>

<h2>How to Use VN Code Pro Templates — Step by Step</h2>
<p>Using VN Code Pro is simple. Here is the exact process:</p>
<ol>
<li><strong>Get QR Code:</strong> After purchase, your unique QR code is delivered instantly to your account dashboard and email. Save the QR code image to your phone's gallery.</li>
<li><strong>Open VN Editor:</strong> Open the free VN Editor app (by Ubiquiti Labs, LLC) on your phone.</li>
<li><strong>Tap Scan Icon:</strong> Look for the scan icon (QR code icon) in the VN app.</li>
<li><strong>Scan QR Code:</strong> Tap the scan icon, then select the QR code image from your phone gallery. The template loads instantly.</li>
<li><strong>Replace Clips:</strong> Tap Use and swap the demo clips with your own photos or videos.</li>
<li><strong>Export and Post:</strong> Tap Export — your reel is ready for Instagram.</li>
</ol>
<p>Full visual guide at <a href="https://vncodepro.com/how-it-works">vncodepro.com/how-it-works</a>. Most creators finish in 4-5 minutes.</p>

<h2>Tips to Get Better Results With {topic['category']}</h2>
<p>[1 sentence intro]</p>
<ul>
<li>[practical tip 1]</li>
<li>[practical tip 2]</li>
<li>[practical tip 3]</li>
<li>[practical tip 4]</li>
<li>[practical tip 5]</li>
</ul>

<h2>What Creators Say About VN Code Pro</h2>
<p><em>"I usually spend a lot of time tweaking small things in my reels, but these templates already feel polished. I just add my clips and post. Simple, clean, and effective."</em> — Influencer</p>
<p><em>"I don't know much about editing, but I still made a great reel for my college fest without any struggle."</em> — College Student</p>
<p><em>"For fashion content, presentation matters a lot. These templates help me keep my feed consistent and trendy without sitting for hours on editing. Definitely worth it."</em> — Fashion Blogger</p>

<h2>Frequently Asked Questions</h2>

<h3>Is VN Code Pro free to use?</h3>
<p>VN Code Pro templates are premium and available at various price points. Check <a href="https://vncodepro.com/templates">vncodepro.com/templates</a> for current pricing. The VN Editor app itself (by Ubiquiti Labs, LLC) is completely free on iOS and Android.</p>

<h3>How do I get my template after purchase?</h3>
<p>After purchase, tap the Download button on the confirmation page. A download link is also sent to your registered email immediately.</p>

<h3>Do I need editing experience?</h3>
<p>No. VN Code Pro templates are designed for complete beginners. If you can tap a few buttons, you can create a professional reel.</p>

<h3>Can I reuse the templates?</h3>
<p>Yes. Every template is a one-time purchase and reusable for unlimited videos.</p>

<h3>What payment methods are accepted?</h3>
<p>VN Code Pro accepts UPI, debit/credit cards, and net banking — all processed securely.</p>

<h3>Is there a current offer?</h3>
<p>Yes — BUY 2 GET 1 FREE on all orders. Use code <strong>B2G1</strong> at checkout.</p>

<h2>Start Creating Better Reels Today</h2>
<p>[2-3 smooth sentences encouraging the reader to visit VN Code Pro. Natural, not pushy. No cliche sign-offs.]</p>
<p>Browse the full <a href="https://vncodepro.com/templates">{topic['category']} collection at VN Code Pro</a> and create your best reel yet. Questions? Reach us at <a href="https://vncodepro.com/contact-us">vncodepro.com/contact-us</a> or <a href="mailto:contact@vncodepro.com">contact@vncodepro.com</a>.</p>

Write the COMPLETE article now. Do not stop early."""

    content = gemini_call(prompt)
    if not content:
        content = ""
    word_count = len(content.split())

    if word_count < 1500:
        print(f"  Too short ({word_count} words) — expanding with Gemini...")
        expand = f"""This blog is only {word_count} words. Expand to at least 1500 words.
Add more detail to each template style section.
Add more specific tips.
Make intro and conclusion longer.
Keep the exact same HTML structure.
Return complete expanded article only.

{content}"""
        content = gemini_call(expand) or content
        word_count = len(content.split())

    print(f"  Written: {word_count} words")
    return content, word_count


# ─── STEP 3.5: Fact-Check — GEMINI (reads whole article) ─────────
def fact_check_blog(content, verified_facts, site_knowledge):
    print("Step 3.5: Fact-checking with Gemini...")

    confirmed_urls = list(verified_facts.get("confirmed_urls", {}).values())

    prompt = f"""You are a strict fact-checker for a VN Code Pro blog post.

CONFIRMED REAL URLS (only these exist — fix any others):
{json.dumps(confirmed_urls, indent=2)}

THINGS TO FIX:
1. Any URL not in confirmed list → replace with https://vncodepro.com
2. "VN Inc" anywhere → replace with "Ubiquiti Labs, LLC"
3. Any unverified number like "10,000 creators", "5x engagement" → remove
4. Any specific price like ₹99 or ₹599 → replace with "check current pricing at vncodepro.com/templates"
5. Any guaranteed ranking claim → remove
6. Duplicate HTML tag <li><li> → fix to single <li>
7. "scan from gallery" → replace with "select the downloaded template file"
8. Step-by-step process must show DOWNLOAD first, not "save QR to gallery"

BLOG TO CHECK:
{content}

Return ONLY the corrected blog HTML. Do not explain changes. Preserve all structure and length."""

    try:
        corrected = gemini_call(prompt)
        if corrected and len(corrected) > 500:
            print("  Fact-check complete")
            return corrected
    except Exception as e:
        print(f"  Fact-check failed, keeping original: {e}")
    return content


# ─── STEP 4: Metadata — GEMINI (structured precision) ────────────
def generate_metadata(topic, content):
    print("Step 4: Generating metadata with Gemini...")

    prompt = f"""Create SEO metadata for a VN Code Pro blog post.

Title: {topic['title']}
Keyword: {topic['keyword']}
Content preview: {content[:400]}

Rules:
- meta_title: include keyword + end with "| VN Code Pro" — max 60 chars — NEVER use "Brand"
- meta_description: include keyword — 140-155 chars exactly — compelling CTA
- slug: lowercase hyphens, include keyword and 2026, max 50 chars
- tags: exactly 5 relevant tags
- excerpt: 2 sentences that make someone want to read

Return ONLY valid JSON:
{{
  "meta_title": "...",
  "meta_description": "...",
  "excerpt": "...",
  "slug": "...",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "image_prompt": "Instagram thumbnail for {topic['keyword']}, vibrant colors, mobile video editing, 4K, 16:9"
}}"""

    raw = gemini_call(prompt, json_mode=True)
    data = parse_json(raw)

    if not data:
        data = {
            "meta_title": topic["title"][:45] + " | VN Code Pro",
            "meta_description": f"Create stunning {topic['keyword']} with VN Code Pro templates. Guide for Indian Instagram creators 2026.",
            "slug": topic["keyword"].replace(" ", "-").lower() + "-2026",
            "tags": ["VN templates", "Instagram Reels", "video editing", "India 2026", topic["category"]],
            "excerpt": f"Discover how to create amazing {topic['keyword']} with VN Code Pro in 2026.",
            "image_prompt": f"Instagram Reel thumbnail for {topic['keyword']}, vibrant modern UI, 4K, 16:9"
        }

    # Enforce brand name
    mt = data.get("meta_title", "")
    if "Brand" in mt:
        mt = mt.replace("Brand", "VN Code Pro")
    if "VN Code Pro" not in mt:
        mt = mt[:45] + " | VN Code Pro"
    if len(mt) > 60:
        mt = mt[:55] + "..."
    data["meta_title"] = mt

    # Enforce description length
    desc = data.get("meta_description", "")
    if len(desc) > 155:
        desc = desc[:155]
        data["meta_description"] = desc[:desc.rfind(" ")]
    elif len(desc) < 130:
        data["meta_description"] = desc + " Explore now at VN Code Pro."

    tags = data.get("tags", [])
    while len(tags) < 5:
        tags.append("VN templates")
    data["tags"] = tags[:5]

    print(f"  Meta title ({len(data['meta_title'])} chars): {data['meta_title']}")
    print(f"  Meta desc  ({len(data['meta_description'])} chars)")
    print(f"  Slug: {data.get('slug', 'N/A')}")
    return data


# ─── STEP 5: Quality Check — GROQ (fast evaluation) ──────────────
def quality_check(content, word_count, keyword):
    print("Step 5: Quality check with Groq...")

    kw_count = content.lower().count(keyword.lower())

    checks = {
        "word_count_1500+":        word_count >= 1500,
        "has_h1":                  content.count("<h1>") == 1,
        "has_5+_h2_headings":      content.count("<h2>") >= 5,
        "has_4+_h3_sections":      content.count("<h3>") >= 4,
        "has_numbered_steps":      "<ol>" in content,
        "has_3+_bullet_lists":     content.count("<ul>") >= 3,
        "has_5+_internal_links":   content.count("vncodepro.com") >= 5,
        "has_2026_4+_times":       content.count("2026") >= 4,
        "keyword_in_content":      keyword.lower() in content.lower(),
        "keyword_not_stuffed":     2 <= kw_count <= 6,
        "no_broken_fragments":     "And, time-consuming" not in content and "You need help" not in content,
        "has_faq_section":         "Frequently Asked Questions" in content and content.count("<h3>") >= 4,
        "has_testimonials":        "Influencer" in content and "Fashion Blogger" in content,
        "correct_qr_process":      "QR code" in content and "gallery" in content and "VN Inc" not in content,
        "no_fake_stats":           "10,000 creators" not in content and "5x engagement" not in content,
        "no_wrong_developer":      "VN Inc" not in content,
        "has_offer_mentioned":     "B2G1" in content or "BUY 2" in content,
        "no_duplicate_li_tags":    "<li><li>" not in content,
        "correct_url_format":      "/how-it-use" not in content,
        "vncodepro_mentioned_10+": content.lower().count("vn code pro") >= 10
    }

    passed = sum(checks.values())
    total  = len(checks)
    pct    = (passed / total) * 100

    print(f"  Score: {passed}/{total} ({pct:.1f}%)")
    for name, result in checks.items():
        print(f"    {'✅' if result else '❌'} {name.replace('_', ' ')}")

    approved = passed >= 16
    print(f"\n  {'✅ APPROVED' if approved else '⚠️  NEEDS IMPROVEMENT'} — {pct:.1f}%")
    return approved, checks


def fix_quality_mistakes(content, failed_checks, keyword):
    print(f"  [Auto-Fix] Asking Gemini to fix {len(failed_checks)} mistakes...")
    
    specific_instructions = []
    for f in failed_checks:
        if "word count" in f:
            specific_instructions.append("- Expand existing sections with more detail to reach at least 1500 words.")
        elif "has h1" in f:
            specific_instructions.append("- Ensure there is exactly one <h1> heading at the top.")
        elif "h2 headings" in f:
            specific_instructions.append("- Add more <h2> subheadings to break up large sections. Ensure there are at least 5 <h2> tags in total.")
        elif "h3 sections" in f:
            specific_instructions.append("- Add more <h3> subheadings under existing <h2> sections. Ensure there are at least 4 <h3> tags in total.")
        elif "numbered steps" in f:
            specific_instructions.append("- Convert a relevant process (like a how-to section) into an <ol> numbered list with <li> elements.")
        elif "bullet lists" in f:
            specific_instructions.append("- Convert relevant comma-separated points or features into <ul> bullet lists. Need at least 3 <ul> lists.")
        elif "internal links" in f:
            specific_instructions.append("- Naturally integrate links to 'vncodepro.com' across the article. Ensure at least 5 such links exist.")
        elif "2026" in f:
            specific_instructions.append("- Add the year '2026' naturally in at least 4 different places.")
        elif "keyword in content" in f:
            specific_instructions.append(f"- Include the exact keyword '{keyword}' naturally in the text.")
        elif "keyword not stuffed" in f:
            specific_instructions.append(f"- Reduce the usage of the keyword '{keyword}'. Use it only 2 to 6 times total.")
        elif "broken fragments" in f:
            specific_instructions.append("- Fix broken sentence fragments (like 'And, time-consuming' or 'You need help') by merging them into complete, natural sentences.")
        elif "faq section" in f:
            specific_instructions.append("- Add a 'Frequently Asked Questions' <h2> section with at least 4 <h3> questions and <p> answers.")
        elif "testimonials" in f:
            specific_instructions.append("- Add a 'What Creators Say About VN Code Pro' <h2> section with quotes from an 'Influencer' and a 'Fashion Blogger'.")
        elif "qr process" in f:
            specific_instructions.append("- Ensure the QR code process is correct: After purchase, save the QR code image to your phone gallery. Open VN app → tap scan icon → select QR code IMAGE from gallery → tap Use → replace clips → Export.")
        elif "fake stats" in f:
            specific_instructions.append("- Remove fake stats like '10,000 creators' or '5x engagement'.")
        elif "wrong developer" in f:
            specific_instructions.append("- Replace 'VN Inc' with 'Ubiquiti Labs, LLC'.")
        elif "offer mentioned" in f:
            specific_instructions.append("- Mention the current offer: BUY 2 GET 1 FREE (use code B2G1).")
        elif "duplicate li tags" in f:
            specific_instructions.append("- Fix invalid HTML like <li><li> to be a single <li> tag.")
        elif "correct url format" in f:
            specific_instructions.append("- Remove or fix any invalid URLs like '/how-it-use'.")
        elif "vncodepro mentioned" in f:
            specific_instructions.append("- Mention 'VN Code Pro' naturally at least 10 times throughout the article.")
        else:
            specific_instructions.append(f"- Fix this requirement: {f}")

    instructions_text = chr(10).join(specific_instructions)

    prompt = f"""You are a SURGICAL HTML editor. You must fix exactly {len(failed_checks)} quality issues in the provided blog draft.

Focus keyword: {keyword}

THE ISSUES TO FIX:
{instructions_text}

CRITICAL RULES:
1. ONLY apply the minimal required edits to fix the specific issues above.
2. DO NOT rewrite or summarize the rest of the blog.
3. Keep all existing sentences, paragraphs, and HTML structure EXACTLY as they are, unless they directly violate one of the issues above.
4. Output ONLY the fully corrected HTML without any markdown formatting wrappers.

DRAFT TO FIX:
{content}"""
    
    fixed_content = gemini_call(prompt)
    return fixed_content if fixed_content and len(fixed_content) > 500 else content



# ─── STEP 7: Save to Supabase ────────────────────────────────────
def save_draft(topic, content, meta):
    post = {
        "title":            topic["title"],
        "slug":             meta.get("slug", ""),
        "content":          content,
        "excerpt":          meta.get("excerpt", ""),
        "meta_title":       meta.get("meta_title", ""),
        "meta_description": meta.get("meta_description", ""),
        "focus_keyword":    topic["keyword"],
        "tags":             meta.get("tags", []),
        "image_prompt":     meta.get("image_prompt", ""),
        "status":           "draft",
        "pushed_to_api":    False
    }
    result = supabase.table("blog_posts").insert(post).execute()
    if result and result.data:
        first = result.data[0]
        if isinstance(first, dict) and "id" in first:
            return first["id"]
    return ""


# ─── STEP 8A: Save Blog as .txt File ─────────────────────────────
def save_to_txt(topic, content, meta, word_count):
    try:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)

        slug      = meta.get("slug", "blog").replace("/", "-")[:60]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{slug}-{timestamp}.txt"
        filepath  = os.path.join(output_dir, filename)

        tags = meta.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)

        header = (
            "=" * 55 + "\n"
            "  VN CODE PRO BLOG BOT — Generated Blog\n"
            "=" * 55 + "\n"
            f"  Title:        {topic.get('title', '')}\n"
            f"  Keyword:      {topic.get('keyword', '')}\n"
            f"  Slug:         {meta.get('slug', '')}\n"
            f"  Word Count:   {word_count}\n"
            f"  Excerpt:      {meta.get('excerpt', '')}\n"
            f"  Meta Title:   {meta.get('meta_title', '')}\n"
            f"  Meta Desc:    {meta.get('meta_description', '')}\n"
            f"  Tags:         {tags_str}\n"
            f"  Generated:    {datetime.now().strftime('%Y-%m-%d %I:%M %p IST')}\n"
            "=" * 55 + "\n\n"
            "[FULL HTML CONTENT BELOW]\n\n"
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + content)

        print(f"  [SAVED] Blog saved to: output/{filename}")
        return filepath

    except Exception as e:
        print(f"  [WARNING] Could not save .txt file: {e}")
        return None


# ─── STEP 8B: Push to Website API ─────────────────────────────────
def push_to_api(topic, content, meta, word_count, verified_facts, supabase_id=None):
    try:
        BASE_URL = "http://192.168.1.15:8000"

        # ── Auto Login ──
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email":    "vbi@gmail.com",
                "password": "vbi123"
            },
            headers={"Content-Type": "application/json"},
            timeout=5
        )

        if login_resp.status_code != 200:
            print(f"  [AUTH ERROR] Login failed: {login_resp.status_code} — {login_resp.text[:100]}")
            return

        login_data = login_resp.json()
        token = (
            login_data.get("token") or
            login_data.get("accessToken") or
            login_data.get("access_token") or
            login_data.get("data", {}).get("token") or
            login_data.get("data", {}).get("accessToken") or
            ""
        )

        if not token:
            print(f"  [AUTH ERROR] Token not found in response: {login_data}")
            return

        print(f"  [AUTH] Login successful")

        # ── Category ID (hardcoded) ──
        category_id = "00758cab-bd3e-45a1-a7ab-6853aea440e0"

        # ── Build Payload ──
        read_time = max(1, math.ceil(word_count / 200))

        payload = {
            "title":              topic["title"],
            "slug":               meta.get("slug", ""),
            "excerpt":            meta.get("excerpt", ""),
            "content":            content,
            "blogCategoryId":     category_id,
            "coverImageUrl":      "",
            "readTimeMinutes":    read_time,
            "isPublished":        True,
            "publishedAt":        datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "authorName":         "VN Code Pro",
            "metaTitle":          meta.get("meta_title", ""),
            "metaDescription":    meta.get("meta_description", ""),
            "metaKeywords":       topic.get("keyword", ""),
            "ogTitle":            meta.get("meta_title", ""),
            "ogDescription":      meta.get("meta_description", ""),
            "ogImageUrl":         "",
            "canonicalUrl":       f"https://vncodepro.com/blogs/{meta.get('slug', '')}",
            "robotsIndex":        True,
            "structuredDataJson": ""
        }

        # ── Push Blog ──
        r = requests.post(
            f"{BASE_URL}/api/blog/posts",
            json=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {token}"
            },
            timeout=10
        )

        if r.status_code in [200, 201]:
            data = r.json()
            post_id = (
                data.get("id") or
                data.get("data", {}).get("id") or
                "N/A"
            )
            print(f"  [SUCCESS] Blog pushed to website — ID: {post_id}")
            if supabase_id:
                supabase.table("blog_posts").update({"pushed_to_api": True}).eq("id", supabase_id).execute()
            return True
        elif r.status_code == 401:
            print("  [AUTH ERROR] Token rejected — check email and password")
        elif r.status_code == 403:
            print("  [AUTH ERROR] Not enough permissions — account needs admin role")
        else:
            print(f"  [WARNING] API returned {r.status_code}: {r.text[:150]}")

    except requests.exceptions.ConnectionError:
        print("  [WARNING] Website API offline — skipped pushing")
    except Exception as e:
        print(f"  [WARNING] Push failed: {e}")
    
    return False


def retry_failed_pushes():
    try:
        failed = supabase.table("blog_posts").select("*").eq("pushed_to_api", False).execute()
        if not failed.data:
            return

        print(f"Step 0.0: Found {len(failed.data)} blog(s) that failed to push. Retrying...")
        for blog in failed.data:
            if not isinstance(blog, dict):
                continue
            topic = {
                "title": blog.get("title", ""),
                "keyword": blog.get("focus_keyword", "")
            }
            meta = {
                "slug": blog.get("slug", ""),
                "excerpt": blog.get("excerpt", ""),
                "meta_title": blog.get("meta_title", ""),
                "meta_description": blog.get("meta_description", "")
            }
            content = str(blog.get("content", ""))
            word_count = len(content.split())

            success = push_to_api(topic, content, meta, word_count, None, supabase_id=blog.get("id"))
            if success:
                print(f"  ✅ Retry success for: {str(topic['title'])[:40]}...")
            else:
                print(f"  ⚠️ Still offline for: {str(topic['title'])[:40]}...")
    except Exception as e:
        pass

# ─── MAIN ────────────────────────────────────────────────────────
def run():
    print("\n" + "="*52)
    print("  VN CODE PRO BLOG BOT v7")
    print("  Gemini 2.5 Flash + Groq Llama 70B")
    print("  Fact-Checked | Truth-First Output")
    print("="*52 + "\n")

    try:
        retry_failed_pushes()

        print("Step 0.1: Loading site knowledge...")
        site_knowledge = site_crawler.crawl_site()

        print("Step 0.2: Loading verified facts...")
        verified_facts = fact_verifier.verify_facts()

        trends = research_trends()
        if not trends:
            print("No trends found. Check your Tavily API key.")
            log_error("Trend Research", "No trends found. Tavily API key might be exhausted or invalid.")
            return

        topic = decide_topic(trends, site_knowledge, verified_facts)
        if not topic.get("title"):
            print("Could not generate topic. Try again.")
            return

        content, word_count = write_blog(topic, site_knowledge, verified_facts)
        if not content or word_count < 800:
            print(f"Content too short ({word_count} words). Try again.")
            return

        print("  Waiting 10s to avoid API rate limits...")
        time.sleep(10)

        content    = fact_check_blog(content, verified_facts, site_knowledge)
        word_count = len(content.split())

        print("  Waiting 10s to avoid API rate limits...")
        time.sleep(10)

        # ─── STEP 5: Quality Check with Auto-Fix Loop ──────────────
        MAX_FIX_ATTEMPTS = 3
        is_perfect = False
        
        for attempt in range(MAX_FIX_ATTEMPTS):
            approved, checks = quality_check(content, word_count, topic.get("keyword", ""))
            
            failed_keys = [k.replace('_', ' ') for k, v in checks.items() if not v]
            
            if not failed_keys:
                print("  ✅ 100% Perfect Score Achieved!")
                is_perfect = True
                break
                
            if attempt < MAX_FIX_ATTEMPTS - 1:
                print(f"  ⚠️ Attempt {attempt+1}: Not 100%. Initiating Auto-Fix...")
                time.sleep(5)
                content = fix_quality_mistakes(content, failed_keys, topic.get("keyword", ""))
                word_count = len(content.split())
            else:
                print(f"  ❌ Reached max auto-fix attempts. Failed to reach 100%.")
        
        if not is_perfect:
            print("  [ABORT] Blog did not achieve a perfect score. Discarding draft.")
            log_error("Quality Check", "Blog failed to achieve 100% after 3 auto-fix attempts. Draft discarded.")
        else:
            meta = generate_metadata(topic, content)
            post_id  = save_draft(topic, content, meta)

            print("\n" + "="*52)
            print("  BLOG GENERATED SUCCESSFULLY!")
            print("="*52)
            print(f"  Title:    {topic['title'][:55]}")
            print(f"  Keyword:  {topic['keyword']}")
            print(f"  Words:    {word_count}")
            if post_id:
                print(f"  DB ID:    {post_id}")
            save_to_txt(topic, content, meta, word_count)
            # push_to_api(topic, content, meta, word_count, verified_facts, supabase_id=post_id)

        print(f"\n  API Usage:")
        print(f"    Gemini calls:    {API_USAGE['gemini_calls']} ({API_USAGE['gemini_tokens']} tokens)")
        print(f"    Groq calls:      {API_USAGE['groq_calls']} ({API_USAGE['groq_tokens']} tokens)")
        print(f"    Tavily searches: {API_USAGE['tavily_searches']}")
        print(f"    Supabase posts:  {API_USAGE['supabase_posts']}")

    except Exception as e:
        print(f"\nError: {str(e)[:150]}")
        print("Check your API keys and try again.")
        log_error("Main Run Loop", f"Unexpected crash: {str(e)}")


if __name__ == "__main__":
    run()
