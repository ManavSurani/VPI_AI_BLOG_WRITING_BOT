# VN Code Pro Blog Bot 🤖✍️

An advanced, fully autonomous AI blog generation pipeline that writes, fact-checks, quality-checks, and publishes SEO-optimized blogs directly to your CMS and Supabase database.

## 🌟 Key Features

- **Truth-First Architecture**: Combines `Tavily` web search with an internal `site_crawler.py` and `fact_verifier.py` to ensure high-accuracy content without hallucinations.
- **Multi-Model Pipeline**: 
  - **Trend Research & Topic Decision**: Uses Groq (Llama 70B) to analyze search trends and decide on the best, most relevant blog topics.
  - **Blog Generation**: Uses Google's Gemini 2.5 Flash for high-quality, long-form content creation.
- **Automated Quality Control**: Built-in quality checks for word counts, H2 presence, and specific instructional adherence. Automatically uses Gemini to "surgically edit" and fix mistakes without rewriting unrelated sections.
- **Robust Key Management**: Custom `key_manager.py` with automatic API key rotation and exponential backoff to handle 429/503 errors and daily quotas seamlessly.
- **API Integration**: Provides a FastAPI backend (`api.py`) that integrates directly into your admin panel, allowing you to trigger blog generation and update API keys dynamically.
- **Resource Tracking**: Real-time API usage and token limit tracking to monitor free-tier usage efficiently.

## 📁 Project Structure

```
vncodepro-blog-bot/
├── api.py               # FastAPI server for webhook triggers and admin UI integration
├── main.py              # The core AI blog generation pipeline
├── key_manager.py       # API key rotation and robust error handling
├── site_crawler.py      # Crawls your site to build internal knowledge for fact-checking
├── fact_verifier.py     # Two-pass AI fact-checking against web & internal knowledge
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (API keys, Supabase credentials)
└── .gitignore
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Variables
Create a `.env` file in the root directory (or use the `/save-env` admin endpoint):
```env
GEMINI_API_KEY="your-gemini-key-1,your-gemini-key-2"
GROQ_API_KEY="your-groq-key"
TAVILY_API_KEY="your-tavily-key"
SUPABASE_URL="your-supabase-url"
SUPABASE_KEY="your-supabase-anon-key"
```

### 3. Run the Bot Manually
You can trigger a single blog generation directly from the terminal:
```bash
python main.py
```

### 4. Run the API Server
To expose the bot to your website's admin panel:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```
*(Note: In production, it is recommended to run this using PM2 so it auto-restarts and stays alive in the background.)*

## ⚙️ How It Works

1. **Trend Research**: Scans recent internet trends using Tavily.
2. **Topic Decision**: Groq AI selects the most viable, SEO-friendly topic.
3. **Draft Generation**: Gemini 2.5 Flash drafts the blog post with rich HTML formatting.
4. **Fact-Checking**: The draft is cross-referenced with your internal site knowledge and live web search to remove fabrications.
5. **Quality Check**: The post is scored on various criteria (e.g., word count, formatting). Failed checks are auto-fixed surgically.
6. **Publishing**: The final verified blog is saved to Supabase and pushed to your custom CMS API.

## 📊 API & Resource Limits Monitoring

The bot automatically prints a detailed **API LIMIT & RESOURCE USAGE** summary table at the end of every successful run, helping you stay within Groq/Tavily/Gemini free-tier limits.
