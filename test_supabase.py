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
row = result.data[0] if result.data else {}
if isinstance(row, dict):
    print("Post ID:", row.get("id"))
    print("Title:", row.get("title"))
    print("Status:", row.get("status"))
print("\nSupabase working! Phase 2 complete.")
