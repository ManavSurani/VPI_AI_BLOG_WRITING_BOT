from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()

print("Testing Supabase connection...")
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

test_post = {
    "title": "Test Blog Post",
    "slug": "test-blog-post",
    "content": "<p>This is a test post from the bot.</p>",
    "excerpt": "Test excerpt",
    "meta_title": "Test Blog Post | VNCodePro",
    "meta_description": "This is a test meta description for the blog post.",
    "focus_keyword": "test",
    "tags": ["test", "vncodepro"],
    "image_prompt": "test image prompt",
    "status": "draft"
}

result = supabase.table("blog_posts").insert(test_post).execute()
print("Saved to Supabase!")
print("Post ID:", result.data[0]["id"])
print("Title:", result.data[0]["title"])
print("Status:", result.data[0]["status"])
print("\nSupabase working! Phase 2 complete.")
