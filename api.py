from fastapi import FastAPI, BackgroundTasks, Header, HTTPException
import subprocess
from pydantic import BaseModel
from typing import List
from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = "vncodepro-bot-secret-key-2026"
app = FastAPI(title="VN Code Pro Blog Bot API")
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

class Blog(BaseModel):
    topic: str
    title: str
    slug: str
    keyword: str
    category: str
    word_count: int
    offer: str
    excerpt: str
    image_prompt: str
    tags: List[str]
    content_html: str

@app.post("/blogs")
def receive_blog(blog: Blog):
    print(f"[API] Received: {blog.title}")
    return {"status": "success", "title": blog.title}

@app.get("/blogs")
def list_blogs():
    result = supabase.table("blog_posts").select("id, title, slug, excerpt").execute()
    return result.data

@app.get("/blogs/{slug}")
def get_blog(slug: str):
    result = supabase.table("blog_posts").select("*").eq("slug", slug).execute()
    if not result.data:
        return {"error": "Blog not found"}
    return result.data[0]

@app.post("/generate-blog")
def trigger_blog(
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(None)
):
    # Check API key
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # Run bot in background
    background_tasks.add_task(run_bot)

    return {
        "status": "success",
        "message": "Blog generation started! Will be live in 2-3 minutes."
    }

def run_bot():
    subprocess.run(
        ["python", "main.py"],
        cwd="c:\\Vs\\vncodepro-blog-bot"
    )
