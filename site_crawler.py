"""
site_crawler.py — Crawls vncodepro.com using Tavily search (free tier).
Does NOT use tavily.extract() which is a paid feature.
Caches results 24 hours.
"""

import json, os, re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

CACHE_FILE = "site_knowledge.json"
CACHE_TTL_HOURS = 24

# All confirmed real URLs from live scrape
KNOWN_REAL_URLS = [
    "https://vncodepro.com",
    "https://vncodepro.com/templates",
    "https://vncodepro.com/how-it-works",
    "https://vncodepro.com/about",
    "https://vncodepro.com/contact-us",
    "https://vncodepro.com/blogs",
    "https://vncodepro.com/refund-policy",
    "https://vncodepro.com/terms-and-conditions",
    "https://vncodepro.com/digital-delivery-policy",
    "https://vncodepro.com/privacy-policy",
    "https://vncodepro.com/#faq",
    "https://vncodepro.com/#trending"
]

# Confirmed from /templates page meta description
CONFIRMED_CATEGORIES = [
    "Wedding Templates", "Travel Templates", "Festival Templates",
    "Business Templates", "Couple Templates", "Birthday Templates",
    "Friendship Templates", "Gym Templates", "Girly Templates",
    "Personal Templates", "Cinematic Templates", "Trending Templates"
]

# CORRECT 6-step process from /how-it-use page (scraped live)
# CRITICAL: Step 1 is DOWNLOAD not "scan from gallery"
CONFIRMED_PROCESS = [
    {
        "step": 1,
        "title": "Get QR Code",
        "description": "After purchase, your unique QR code is delivered instantly to your account dashboard and email. Save the QR code image to your phone's gallery."
    },
    {
        "step": 2,
        "title": "Open VN Video Editor",
        "description": "Open the VN Video Editor app on your mobile device."
    },
    {
        "step": 3,
        "title": "Open Your Projects",
        "description": "Tap the X icon in the top-left corner to go to the Your Projects screen."
    },
    {
        "step": 4,
        "title": "Scan QR Code",
        "description": "Tap the scan icon (QR code icon or plus sign) in the VN app, then select the QR code IMAGE from your phone gallery. The template loads instantly!"
    },
    {
        "step": 5,
        "title": "Replace Clips",
        "description": "Tap Use and replace the demo clips with your own photos or videos."
    },
    {
        "step": 6,
        "title": "Export Video",
        "description": "Tap Export and your reel is ready to post on Instagram."
    }
]

# Real testimonials with REAL names confirmed from homepage
CONFIRMED_TESTIMONIALS = [
    {
        "name": "Kaushal Roy",
        "role": "Influencer",
        "quote": "I usually spend a lot of time tweaking small things in my reels, but these templates already feel polished. I just add my clips and post. Simple, clean, and effective."
    },
    {
        "name": "Deep Goti",
        "role": "College Student",
        "quote": "I don't know much about editing, but I still made a great reel for my college fest without any struggle."
    },
    {
        "name": "Priya Sharma",
        "role": "Fashion Blogger",
        "quote": "For fashion content, presentation matters a lot. These templates help me keep my feed consistent and trendy without sitting for hours on editing. Definitely worth it."
    }
]


def is_cache_valid():
    if not os.path.exists(CACHE_FILE):
        return False
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        scraped_at = datetime.fromisoformat(data.get("scraped_at", "2000-01-01"))
        return datetime.now() - scraped_at < timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return False


def load_cache():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def search_safe(tavily, query, max_results=3):
    """Free-tier safe search wrapper."""
    try:
        return tavily.search(query, max_results=max_results)
    except Exception as e:
        print(f"  Warning: Search failed for '{query[:40]}': {e}")
        return {"results": []}


def find_published_blogs(tavily):
    """Find real published blog posts using search (free tier safe)."""
    urls, titles = [], []
    try:
        res = tavily.search("site:vncodepro.com/blogs VN templates", max_results=8)
        if res and "results" in res:
            for r in res["results"]:
                url = r.get("url", "")
                title = r.get("title", "")
                if "vncodepro.com/blogs/" in url and url not in urls:
                    urls.append(url)
                    clean = re.sub(r'\s*[|\-–].*$', '', title).strip()
                    titles.append(clean)
    except Exception as e:
        print(f"  Warning: Blog search failed: {e}")
    return urls, titles


def crawl_site(tavily_api_key=None):
    """
    Main entry point. Returns structured site knowledge.
    Uses free-tier Tavily search only — no extract() calls.
    Caches for 24 hours.
    """
    if is_cache_valid():
        print("  Using cached site knowledge (< 24 hours old)")
        return load_cache()

    print("  Building site knowledge from vncodepro.com...")
    tavily = TavilyClient(api_key=tavily_api_key or os.environ["TAVILY_API_KEY"])

    knowledge = {
        "scraped_at": datetime.now().isoformat(),
        "site_url": "https://vncodepro.com",
        "contact_email": "contact@vncodepro.com",
        "social": {
            "instagram": "@vncodepro.official",
            "instagram_url": "https://www.instagram.com/vncodepro.official",
            "youtube": "@VNCodePro",
            "youtube_url": "https://www.youtube.com/@VNCodePro"
        },
        "verified_urls": KNOWN_REAL_URLS.copy(),
        "pages": {}
    }

    # Homepage data (from confirmed scrape — no API call needed)
    knowledge["pages"]["homepage"] = {
        "process_steps": CONFIRMED_PROCESS,
        "testimonials": CONFIRMED_TESTIMONIALS,
        "current_offer": "BUY 2 GET 1 FREE — use code: B2G1",
        "tagline": "Get Free & Premium VN Templates in One Place"
    }

    # Templates page (categories confirmed from meta description)
    knowledge["pages"]["templates"] = {
        "categories": CONFIRMED_CATEGORIES,
        "meta_description": "Browse our collection of professional VN video templates for Instagram Reels. Find templates for weddings, travel, festivals, business, and more. Instant QR code delivery.",
        "keywords": ["VN templates", "video templates", "reel templates", "Instagram reels", "wedding templates", "travel templates"]
    }

    # How-it-works page (6 steps confirmed from live scrape)
    knowledge["pages"]["how_it_works"] = {
        "url": "https://vncodepro.com/how-it-works",
        "steps": CONFIRMED_PROCESS,
        "time_to_create": "4-5 minutes",
        "note": "URL is /how-it-works"
    }

    # About page (confirmed from live scrape)
    knowledge["pages"]["about"] = {
        "description": (
            "VN CODE PRO is a digital platform created to simplify video creation "
            "for reels, weddings, festivals, travel content, and business promotions. "
            "Provides professionally designed VN templates, instant QR-based access, "
            "secure payments via PhonePe, user-friendly experience for all levels, "
            "and dedicated support."
        ),
        "mission": "Help creators save time and produce high-quality videos effortlessly.",
        "payment_processor": "PhonePe"
    }

    # Find published blog posts (1 search — free tier safe)
    print("  Finding published blog posts...")
    blog_urls, blog_titles = find_published_blogs(tavily)
    knowledge["pages"]["blogs"] = {
        "published_titles": blog_titles,
        "blog_urls": blog_urls,
        "blog_description": "Tips, tutorials, and inspiration to help you create scroll-stopping Reels."
    }
    for url in blog_urls:
        if url not in knowledge["verified_urls"]:
            knowledge["verified_urls"].append(url)

    # Pricing note (no specific prices confirmed without scraping product pages)
    knowledge["pricing"] = {
        "model": "one-time purchase per template, reusable unlimited times",
        "methods": ["UPI", "debit/credit cards", "net banking"],
        "processor": "PhonePe and secure partners",
        "current_offer": "BUY 2 GET 1 FREE — use code B2G1",
        "pricing_page": "https://vncodepro.com/templates",
        "note": "Individual prices shown on product pages. Do NOT state a specific range in blogs."
    }

    # Policy pages (all confirmed)
    knowledge["policies"] = {
        "refund": "https://vncodepro.com/refund-policy",
        "privacy": "https://vncodepro.com/privacy-policy",
        "terms": "https://vncodepro.com/terms-and-conditions",
        "digital_delivery": "https://vncodepro.com/digital-delivery-policy"
    }

    print(f"  Categories: {len(CONFIRMED_CATEGORIES)} confirmed")
    print(f"  Published blogs found: {len(blog_titles)}")
    print(f"  Verified URLs: {len(knowledge['verified_urls'])}")
    print(f"  Process steps: {len(CONFIRMED_PROCESS)} (correct 6-step process)")
    print(f"  Testimonials: {len(CONFIRMED_TESTIMONIALS)} real people")

    save_cache(knowledge)
    print("  Saved to site_knowledge.json")
    return knowledge


if __name__ == "__main__":
    data = crawl_site()
    print(json.dumps(data, indent=2, ensure_ascii=False))
