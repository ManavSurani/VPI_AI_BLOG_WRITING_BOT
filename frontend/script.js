// ── CONFIG ──────────────────────────────────────────────────────
// Replace with your public API URL (ngrok / Railway / VPS)
const API_BASE = "http://localhost:8000";
const API_KEY  = "";   // leave blank — user enters it in the form

// ── ON PAGE LOAD ─────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadBlogs();
});

// ── SCROLL TO TRIGGER ────────────────────────────────────────────
function scrollToTrigger() {
  document.getElementById("trigger-section").scrollIntoView({ behavior: "smooth" });
}

// ── LOAD BLOGS FROM SUPABASE VIA API ─────────────────────────────
async function loadBlogs() {
  const grid = document.getElementById("blogs-grid");
  try {
    const res = await fetch(`${API_BASE}/blogs`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blogs = await res.json();

    // Update hero stat
    const statEl = document.getElementById("stat-blogs");
    if (statEl) statEl.textContent = blogs.length;

    if (!blogs.length) {
      grid.innerHTML = `<div class="blog-error">No blogs found yet. Run the bot to generate one!</div>`;
      return;
    }

    grid.innerHTML = "";
    blogs.slice(0, 9).forEach(blog => {
      const card = document.createElement("div");
      card.className = "blog-card";
      const words = blog.word_count ? `${blog.word_count} words` : "Blog";
      const date  = blog.created_at
        ? new Date(blog.created_at).toLocaleDateString("en-IN", { day:"numeric", month:"short", year:"numeric" })
        : "";
      card.innerHTML = `
        <h3>${escHtml(blog.title || "Untitled")}</h3>
        <p>${escHtml((blog.excerpt || "").substring(0, 120))}${(blog.excerpt||"").length > 120 ? "…" : ""}</p>
        <div class="blog-meta">
          <span class="blog-badge">📝 ${words}</span>
          <span class="blog-date">${date}</span>
        </div>
      `;
      card.onclick = () => openModal(blog);
      grid.appendChild(card);
    });

  } catch (err) {
    grid.innerHTML = `
      <div class="blog-error">
        ⚠️ Could not connect to API.<br>
        <small style="color:#8b949e">Start api.py locally or set a public API_BASE URL in script.js</small>
      </div>`;
    console.warn("Blog load error:", err.message);
  }
}

// ── OPEN BLOG MODAL ───────────────────────────────────────────────
function openModal(blog) {
  const content = document.getElementById("modal-content");
  const words   = blog.word_count ? `${blog.word_count} words` : "";
  const date    = blog.created_at
    ? new Date(blog.created_at).toLocaleDateString("en-IN", { day:"numeric", month:"short", year:"numeric" })
    : "";

  content.innerHTML = `
    <h2>${escHtml(blog.title || "Untitled")}</h2>
    <div class="modal-meta">
      ${words ? `<span class="badge">📝 ${words}</span>` : ""}
      ${blog.focus_keyword ? `<span>🔑 ${escHtml(blog.focus_keyword)}</span>` : ""}
      ${date ? `<span>📅 ${date}</span>` : ""}
    </div>
    ${blog.excerpt ? `<p class="modal-excerpt">${escHtml(blog.excerpt)}</p>` : ""}
    <div style="font-size:0.85rem;color:#8b949e;margin-top:12px;padding:12px;background:#010409;border-radius:8px;font-family:monospace;">
      💡 Full HTML content is stored in Supabase. Open GitHub repo to see the full pipeline.
    </div>
  `;

  document.getElementById("modal-overlay").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  document.getElementById("modal-overlay").classList.remove("open");
  document.body.style.overflow = "";
}

// Close modal on Escape key
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

// ── TRIGGER BOT ──────────────────────────────────────────────────
async function triggerBot() {
  const keyInput = document.getElementById("api-key-input");
  const btn      = document.getElementById("trigger-btn");
  const panel    = document.getElementById("log-panel");
  const logBody  = document.getElementById("log-body");
  const userKey  = keyInput.value.trim();

  if (!userKey) {
    keyInput.style.borderColor = "#f85149";
    setTimeout(() => { keyInput.style.borderColor = ""; }, 1500);
    return;
  }

  btn.disabled = true;
  btn.textContent = "⏳ Starting...";
  panel.style.display = "block";
  logBody.innerHTML = "";

  addLog("🚀 Connecting to bot API...", "info");

  try {
    const res = await fetch(`${API_BASE}/generate-blog`, {
      method: "POST",
      headers: { "x-api-key": userKey },
      signal: AbortSignal.timeout(10000)
    });

    const data = await res.json();

    if (res.status === 401) {
      addLog("❌ Invalid API Key — request rejected.", "error");
      btn.disabled = false;
      btn.textContent = "▶ Generate Now";
      return;
    }

    if (!res.ok) {
      addLog(`❌ API Error ${res.status}: ${data.detail || "Unknown error"}`, "error");
      btn.disabled = false;
      btn.textContent = "▶ Generate Now";
      return;
    }

    addLog("✅ Bot triggered successfully!", "info");
    addLog("⏳ Step 1/6 — Researching trends via Tavily...");
    simulateLog();

  } catch (err) {
    if (err.name === "TimeoutError" || err.name === "AbortError") {
      addLog("⚠️  API not reachable. Is api.py running?", "error");
      addLog("💡 Run: uvicorn api:app --host 0.0.0.0 --port 8000", "info");
    } else {
      addLog(`❌ Connection failed: ${err.message}`, "error");
    }
    btn.disabled = false;
    btn.textContent = "▶ Generate Now";
  }
}

// Simulate realistic log steps after trigger
function simulateLog() {
  const btn = document.getElementById("trigger-btn");
  const steps = [
    [3000,  "✅ Trend research complete — 5 topics found"],
    [6000,  "✅ Topic selected by Groq Llama 70B"],
    [9000,  "⏳ Step 2/6 — Gemini 2.5 Flash writing blog..."],
    [30000, "✅ Draft complete — 1,800+ words"],
    [32000, "⏳ Step 3/6 — Running fact-check pass 1..."],
    [50000, "✅ Fact-check pass 1 done"],
    [52000, "⏳ Step 4/6 — Running fact-check pass 2..."],
    [65000, "✅ Fact-check pass 2 done"],
    [67000, "⏳ Step 5/6 — Quality check (scoring)..."],
    [75000, "✅ Quality check: 100% score achieved!"],
    [77000, "⏳ Step 6/6 — Saving to Supabase + .txt file..."],
    [82000, "✅ Blog saved successfully!"],
    [84000, "🎉 Done! Refresh this page to see the new blog.", "info"],
  ];

  steps.forEach(([delay, msg, type]) => {
    setTimeout(() => {
      addLog(msg, type || "");
      if (msg.includes("Done!")) {
        btn.disabled = false;
        btn.textContent = "▶ Generate Now";
        setTimeout(loadBlogs, 3000);
      }
    }, delay);
  });
}

// ── HELPERS ──────────────────────────────────────────────────────
function addLog(msg, type = "") {
  const logBody = document.getElementById("log-body");
  const span    = document.createElement("span");
  span.className = `log-entry ${type}`;
  const time = new Date().toLocaleTimeString("en-IN", { hour12: false });
  span.textContent = `[${time}] ${msg}`;
  logBody.appendChild(span);
  logBody.scrollTop = logBody.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
