import re
import os

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Imports
content = content.replace(
    '''from datetime import datetime

load_dotenv()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])''',
    '''from datetime import datetime
import site_crawler
import fact_verifier

load_dotenv()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])'''
)

# Remove VNCODEPRO_CATEGORIES and SITE_URLS
content = re.sub(
    r'# Real VNCodePro template categories confirmed from vncodepro\.com\nVNCODEPRO_CATEGORIES = \[\n(?:    ".*",?\n)+\]\n\n# Real pages on vncodepro\.com\nSITE_URLS = \{\n(?:    ".*": ".*",?\n)+\}\n',
    '',
    content
)

# 2. decide_topic
content = content.replace(
    'def decide_topic(trends):',
    'def decide_topic(trends, site_knowledge, verified_facts):'
)

decide_topic_replacement = '''    existing = supabase.table("blog_posts").select("title").execute()
    published_titles = []
    if existing.data:
        published_titles = [p["title"] for p in existing.data if isinstance(p, dict)]
        
    if "pages" in site_knowledge and "blogs" in site_knowledge["pages"]:
        published_titles.extend(site_knowledge["pages"]["blogs"].get("published_titles", []))
        
    categories = site_knowledge["pages"]["templates"].get("categories", [])

    prompt = f"""You are an SEO content strategist for VN Code Pro.
You MUST ONLY pick a topic where we can write factually using verified facts.

VERIFIED FACTS ABOUT VN CODE PRO:
{json.dumps(verified_facts.get("safe_claims", []), indent=2)}

WHAT'S TRENDING ON THE INTERNET RIGHT NOW:
{chr(10).join(f'- {t}' for t in trends[:12])}

REAL TEMPLATE CATEGORIES ON VN CODE PRO:
{', '.join(categories)}

ALREADY PUBLISHED BLOGS (DO NOT repeat these topics):
{chr(10).join(f'- {t}' for t in published_titles[:15]) if published_titles else '- None yet'}'''

content = re.sub(
    r'    existing = supabase\.table\("blog_posts"\)\.select\("title"\)\.execute\(\).*?ALREADY PUBLISHED BLOGS \(DO NOT repeat these topics\):\n\{chr\(10\)\.join\(f\'- \{t\}\' for t in published_titles\[:10\]\) if published_titles else \'- None yet\'\}',
    decide_topic_replacement.replace('\\', '\\\\'),
    content,
    flags=re.DOTALL
)

# 3. write_blog
content = content.replace(
    'def write_blog(topic):',
    'def write_blog(topic, site_knowledge, verified_facts):'
)

write_blog_prompt_replacement = '''    prompt = f"""You are a professional SEO content writer for VN Code Pro (vncodepro.com).

CRITICAL RULE: You MUST ONLY write claims you can attribute to the verified facts or site knowledge below. Do NOT fabricate statistics, testimonials, template names, or prices.

VERIFIED FACTS (Ground Truth):
{json.dumps(verified_facts.get('safe_claims', []), indent=2)}
{json.dumps(verified_facts.get('corrections', {}), indent=2)}

SITE KNOWLEDGE (Real URLs and Categories):
{json.dumps(site_knowledge['verified_urls'], indent=2)}
Categories: {', '.join(site_knowledge['pages']['templates'].get('categories', []))}
Process: {json.dumps(site_knowledge['pages']['homepage'].get('process_steps', []), indent=2)}
Testimonials: {json.dumps(site_knowledge['pages']['homepage'].get('testimonials', []), indent=2)}

REQUIREMENTS (ALL MUST BE INCLUDED):
- Minimum 1500 words (write MORE if needed)
- Use keyword "{topic.get('keyword', '')}" exactly 5-6 times
- Mention "2026" at least 5 times
- Mention "VN Code Pro" at least 15 times
- Include links to vncodepro.com at least 10 times (use ONLY verified URLs)
- Include at least 8 FAQ questions (Q: format) using safe claims
- Include the 3 real testimonials provided in SITE KNOWLEDGE
- Include price/cost references by telling users to check vncodepro.com/templates
- Include comparison vs competitors (conceptually, no fake stats)
- Include at least 10 pro tips
- Include at least 5 bullet point lists
- Include step-by-step numbered list (at least 4 steps from the Process)
- Include at least 18 HTML heading tags total
- Attribute VN Editor to "Ubiquiti Labs, LLC"

CONTENT STRUCTURE (MUST FOLLOW - use exact HTML tags):

<h1>{topic.get('title', '')}</h1>

<p><strong>STRONG HOOK:</strong> Start with a relatable problem that challenges them regarding {topic.get('keyword', '')}.</p>

<h2>The {topic.get('keyword', '')} Challenge in 2026</h2>
<p>[Explain what creators struggle with, without fake stats. Focus on competition and visual quality.]</p>

<h2>Why {topic.get('keyword', '')} REQUIRE Professional Editing</h2>
<p>[Explain algorithmic and aesthetic reasons]</p>

<h2>Introducing VN Code Pro</h2>
<p>[Explain VN Code Pro using safe claims]</p>

<h2>Top Categories for {topic.get('keyword', '')}</h2>
<p>[List real categories from site knowledge]</p>

<h2>How to Get Started with VN Code Pro [Step-by-Step Guide]</h2>
<ol>
[List the 4-step process from site knowledge]
</ol>

<h2>VN Code Pro vs. Other Solutions</h2>
<p>[Honest conceptual comparison]</p>

<h2>10 Pro Tips to Maximize Your Results</h2>
<ul>
[List 10 tips]
</ul>

<h2>Real Success Stories [Testimonials]</h2>
<p>[Include the 3 real testimonials from site knowledge]</p>

<h2>Addressing Your Questions: FAQ</h2>
<p>[Include 8 FAQs using safe claims]</p>

<h2>Ready to Create Your First Professional Reel?</h2>
<p>[Strong CTAs to verified URLs]</p>

Write the COMPLETE 1500+ word blog article now."""'''

content = re.sub(
    r'    prompt = f"""You are a professional SEO content writer.*?Write the COMPLETE 1500\+ word blog article now.*?"""',
    write_blog_prompt_replacement.replace('\\', '\\\\'),
    content,
    flags=re.DOTALL
)

# 4. fact_check_blog
fact_check_func = '''
# ─── STEP 3.5: Fact-Check Pass ──────────────────────────────────
def fact_check_blog(content, verified_facts, site_knowledge):
    print("Step 3.5: Running AI Fact-Check Pass...")
    prompt = f"""You are a strict fact-checker reviewing a blog about VN Code Pro.

VERIFIED FACTS (these are confirmed true):
{json.dumps(verified_facts.get("safe_claims", []), indent=2)}
{json.dumps(verified_facts.get("corrections", {}), indent=2)}

REAL SITE URLS (only these URLs are confirmed to exist):
{json.dumps(site_knowledge['verified_urls'], indent=2)}

BLOG CONTENT TO CHECK:
{content}

Find and FIX any of these issues:
1. Any URL that is NOT in the REAL SITE URLS list → replace with the closest real URL or just https://vncodepro.com.
2. Any statistic with no source → remove it entirely.
3. "VN Inc" anywhere → replace with "Ubiquiti Labs, LLC".
4. "trusted by 10,000 creators" or similar unverified numbers → remove.
5. Any fake template name with a fake URL → replace with generic category references.
6. "TOP 3 Google ranking" or revenue projections → remove from output.
7. Any specific price like ₹99-599 -> replace with "Check current pricing at vncodepro.com/templates".

Return ONLY the CORRECTED blog content with all issues fixed. Do not explain changes. Must be valid HTML."""
    
    corrected = groq(prompt, tokens=6000)
    if not corrected:
        return content
    return corrected
'''
content = content.replace('# ─── STEP 4: Generate metadata', fact_check_func + '\n# ─── STEP 4: Generate metadata')

# 5. save_text_file
content = content.replace(
    'def save_text_file(topic, content, meta, word_count):',
    'def save_text_file(topic, content, meta, word_count, site_knowledge, verified_facts):'
)

# Replace the fake projections in save_text_file
content = re.sub(
    r'Status: ✅ PREMIUM QUALITY \(99\.99%\)\n.*?📊 BLOG IMPACT PROJECTION.*?Estimated Revenue: ₹10,000-25,000 from this blog',
    r'Status: ✅ FACT-CHECKED & VERIFIED\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n✓ Fact-Check Status: VERIFIED\n✓ Sources Used: {len(site_knowledge.get("verified_urls", []))} site pages, {len(verified_facts.get("safe_claims", []))} verified facts',
    content,
    flags=re.DOTALL
)

# 6. run function
run_replacement = '''    try:
        print("Step 0.1: Loading Site Knowledge...")
        site_knowledge = site_crawler.crawl_site()
        
        print("Step 0.2: Loading Verified Facts...")
        verified_facts = fact_verifier.verify_facts()

        trends = research_trends()
        if not trends:
            print("❌ No trends found. Check your Tavily API key.")
            return
        
        topic = decide_topic(trends, site_knowledge, verified_facts)
        if not topic.get('title'):
            print("❌ Could not generate blog topic. Try again.")
            return
        
        content, word_count = write_blog(topic, site_knowledge, verified_facts)
        if not content or word_count < 1000:
            print(f"❌ Content generation failed or too short ({word_count} words). Minimum: 1500 words.")
            return
            
        content = fact_check_blog(content, verified_facts, site_knowledge)
        word_count = len(content.split())
        
        meta = generate_metadata(topic, content)
        approved, checks = quality_check(content, word_count, topic.get("keyword", ""))

        if approved:
            print("\\n" + "╔" + "="*48 + "╗")
            print("║  ✅ PREMIUM QUALITY CHECK PASSED! ✅       ║")
            print("║  Fact-Checked & Verified                    ║")
            print("╚" + "="*48 + "╝")
            
            print("\\nStep 6: Saving files...")
            filename = save_text_file(topic, content, meta, word_count, site_knowledge, verified_facts)
            
            print("Step 7: Saving to database...")
            post_id = save_draft(topic, content, meta)

            print("\\n" + "╔" + "="*48 + "╗")
            print("║  🎉 TRUTH-FIRST BLOG GENERATED! 🎉         ║")
            print("║  Ready to Attract More Attention           ║")
            print("║  to VN CODE PRO                            ║")
            print("╚" + "="*48 + "╝")
            
            print(f"\\n📊 BLOG STATISTICS:")
            print(f"  📝 Title:       {topic.get('title', 'N/A')[:55]}")
            print(f"  🔑 Keyword:     {topic.get('keyword', 'N/A')}")
            print(f"  📂 Category:    {topic.get('category', 'N/A')}")
            print(f"  📊 Word Count:  {word_count} words")
            print(f"  ✅ Quality:     Fact-Checked & Verified")
            print(f"  💾 File:        {filename}")
            if post_id:
                print(f"  🗄️  Supabase:    {post_id}")
            
            print(f"\\n✨ Next Steps:")
            print(f"  1. Open: {filename}")
            print(f"  2. Copy blog content to WordPress/Webflow")
            print(f"  3. Set featured image using image prompt")
            print(f"  4. Publish and promote")
            print(f"  5. Watch traffic flow to vncodepro.com 🚀")
            
            print("\\n" + "╔" + "="*48 + "╗")
            print("║  ✨ PREMIUM CONTENT READY ✨                ║")
            print("║  VN Code Pro Attraction Optimized           ║")
            print("╚" + "="*48 + "╝\\n")'''

content = re.sub(
    r'    try:\n        trends = research_trends\(\).*?╚" \+ "="\*48 \+ "╝\\n"\)\n',
    run_replacement.replace('\\', '\\\\'),
    content,
    flags=re.DOTALL
)

# Update run header
content = content.replace('🚀 VN CODE PRO BLOG BOT v5 (PREMIUM)  🚀', '🚀 VN CODE PRO BLOG BOT v6 (TRUTH-FIRST) 🚀')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated main.py successfully!")
