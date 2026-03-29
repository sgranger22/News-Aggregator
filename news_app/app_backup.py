import streamlit as st
import feedparser
import requests
import re
import json
import os
from openai import OpenAI

st.set_page_config(page_title="V's News Aggregator", layout="wide")

st.title("V's News Aggregator")
st.markdown("Stay updated with curated headlines from your selected sources.")

# ================== STYLE ==================
st.markdown("""
<style>
body {
    background-color: #f7f9fc;
}

.article-card {
    padding: 18px;
    border-radius: 12px;
    background-color: #ffffff;
    margin-bottom: 18px;
    border: 1px solid #e6e6e6;
    transition: all 0.2s ease-in-out;
}

.article-card:hover {
    transform: translateY(-2px);
    box-shadow: 0px 4px 12px rgba(0,0,0,0.08);
}

.article-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 6px;
}

.article-meta {
    font-size: 12px;
    color: #777;
    margin-bottom: 10px;
}

.source-header {
    margin-top: 40px;
    margin-bottom: 15px;
}

a {
    color: #1a73e8;
    font-weight: 500;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* Sidebar labels - keep dark */
section[data-testid="stSidebar"] label p {
    color: #1f2937 !important;
    opacity: 1 !important;
}

/* Make selected checkbox bold */
section[data-testid="stSidebar"] input:checked + div p {
    font-weight: 600 !important;
}

/* ===== Sidebar hover ===== */
section[data-testid="stSidebar"] label:hover {
    background-color: #f5f7fb;
    border-radius: 6px;
}

/* ===== Selected source highlight ===== */
section[data-testid="stSidebar"] input:checked + div {
    background-color: #eef3ff;
    border-radius: 8px;
    padding: 6px 8px;
    border: 1px solid #d8e5ff;
    width: 100%;
}

/* ===== Better text readability ===== */
.article-card p {
    line-height: 1.5;
}

/* ===== Blue success box instead of green ===== */
div[data-testid="stAlert"][role="alert"] {
    background-color: #e6f0ff !important;
    color: #1a3d7c !important;
    border: 1px solid #cce0ff !important;
}

div[data-testid="stAlert"] p {
    color: #1a3d7c !important;
}

/* ===== Softer delete buttons ===== */
section[data-testid="stSidebar"] button {
    border: 1px solid #d7dde8 !important;
    background-color: #ffffff !important;
    color: #4b5563 !important;
    border-radius: 10px !important;
}

section[data-testid="stSidebar"] button:hover {
    border-color: #bfc8d8 !important;
    background-color: #f8fafc !important;
}

/* ===== FULL ROW SELECTED FIX ===== */
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] > label {
    width: 100% !important;
    display: flex !important;
    align-items: center;
    border-radius: 8px;
    padding: 6px 8px;
}

section[data-testid="stSidebar"] div[data-testid="stCheckbox"] input:checked + div {
    background-color: #eef3ff !important;
    border: 1px solid #d8e5ff !important;
    border-radius: 8px;
    padding: 6px 8px;
    width: 100%;
}

</style>
""", unsafe_allow_html=True)

# ================== DATA ==================
FEEDS_FILE = "feeds.json"

def load_feeds():
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, "r") as f:
            return json.load(f)
    return []

def save_feeds(feed_list):
    with open(FEEDS_FILE, "w") as f:
        json.dump(feed_list, f, indent=2)

def clean_text(text):
    return re.sub(r"<.*?>", "", text)

def simple_summary(text, max_sentences=2):
    sentences = re.split(r'(?<=[.!?]) +', text)
    return " ".join(sentences[:max_sentences])

def matches_keyword(title, summary, keyword, match_mode):
    if not keyword:
        return True

    text = f"{title} {summary}"

    if match_mode == "Contains text":
        return keyword.lower() in text.lower()

    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text, re.IGNORECASE) is not None

def ai_summary(text):
    try:
        client = OpenAI()
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=f"Summarize this news article in 2 concise sentences:\n\n{text}"
        )
        return response.output_text.strip(), None
    except Exception as e:
        return None, f"AI error: {str(e)}"

# ================== SIDEBAR ==================
all_feeds = sorted(load_feeds(), key=lambda f: f.get("name", "").lower())

st.sidebar.header("Sources")

selected_urls = []

for i, feed in enumerate(all_feeds):
    feed_name = feed.get("name", "Unnamed Feed")
    feed_url = feed.get("url", "")

    c1, c2 = st.sidebar.columns([4, 1])

    with c1:
        is_selected = st.checkbox(feed_name, value=True, key=f"src_{feed_url}")
        if is_selected:
            selected_urls.append(feed_url)

    with c2:
        if st.button("X", key=f"delete_{i}"):
            updated_feeds = [f for f in all_feeds if f.get("url") != feed_url]
            save_feeds(updated_feeds)
            st.rerun()

st.sidebar.header("Add New RSS Feed")

new_feed_name = st.sidebar.text_input("Feed name (e.g. Wired)")
new_feed_url = st.sidebar.text_input("Feed URL")

if st.sidebar.button("Save Feed"):
    if not new_feed_name or not new_feed_url:
        st.sidebar.warning("Please enter both a feed name and a feed URL.")
    else:
        new_feed = {"name": new_feed_name.strip(), "url": new_feed_url.strip()}
        already_exists = any(feed.get("url") == new_feed["url"] for feed in all_feeds)

        if already_exists:
            st.sidebar.warning("That feed URL is already saved.")
        else:
            all_feeds.append(new_feed)
            save_feeds(all_feeds)
            st.sidebar.success("Feed saved.")
            st.rerun()

st.sidebar.header("Filters")
keyword = st.sidebar.text_input("Filter by keyword or phrase")
match_mode = st.sidebar.radio("Match mode", ["Exact word", "Contains text"], index=0)

st.sidebar.header("Summary Options")
use_ai = st.sidebar.checkbox("Use AI summaries")

# ================== MAIN ==================
if st.button("Fetch News"):
    if not selected_urls:
        st.warning("Please select at least one RSS feed.")
    else:
        articles_by_source = {}
        headers = {"User-Agent": "Mozilla/5.0"}

        for feed in all_feeds:
            if feed.get("url") not in selected_urls:
                continue

            url = feed.get("url")
            feed_title = feed.get("name", url)

            try:
                response = requests.get(url, headers=headers, timeout=15)
                parsed_feed = feedparser.parse(response.content)

                if feed_title not in articles_by_source:
                    articles_by_source[feed_title] = []

                for entry in parsed_feed.entries[:10]:
                    title = entry.get("title", "")
                    raw_summary = clean_text(entry.get("summary", ""))

                    if not matches_keyword(title, raw_summary, keyword, match_mode):
                        continue

                    if use_ai and raw_summary:
                        ai_text, _ = ai_summary(raw_summary)
                        summary = ai_text if ai_text else simple_summary(raw_summary)
                    else:
                        summary = simple_summary(raw_summary)

                    article = {
                        "title": title,
                        "link": entry.get("link", ""),
                        "summary": summary,
                        "published": entry.get("published", "")
                    }

                    articles_by_source[feed_title].append(article)

            except Exception as e:
                st.error(f"Error reading {url}: {e}")

        total_articles = sum(len(v) for v in articles_by_source.values())

        if total_articles == 0:
            st.warning("No articles match your selection.")
        else:
            st.markdown(f"""
            <div style="
                background-color:#e6f0ff;
                color:#1a3d7c;
                padding:12px 18px;
                border-radius:10px;
                border:1px solid #cce0ff;
                font-weight:600;
                margin-bottom:14px;
            ">
                Showing {total_articles} articles
            </div>
            """, unsafe_allow_html=True)

            for source, articles in articles_by_source.items():
                if not articles:
                    continue

                st.divider()
                st.markdown(f"<div class='source-header'><h2 style='margin-bottom:0;'>{source}</h2></div>", unsafe_allow_html=True)

                for article in articles:
                    st.markdown(f"""
                    <div class="article-card">
                        <div class="article-title">{article['title']}</div>
                        <div class="article-meta">Published: {article['published']}</div>
                        <p>{article['summary']}</p>
                        <a href="{article['link']}" target="_blank"><b>Read full article →</b></a>
                    </div>
                    """, unsafe_allow_html=True)
