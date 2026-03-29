import streamlit as st
import feedparser
import requests
import re
import json
import os
import base64
from openai import OpenAI

st.set_page_config(page_title="V's News Aggregator", layout="wide")

st.title("V's News Aggregator")
st.markdown("Stay updated with curated headlines from your selected sources.")

# ================== STYLE ==================
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
    transform: translateY(-3px);
    box-shadow: 0px 6px 18px rgba(0,0,0,0.10);
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
    margin-top: 4px;
    margin-bottom: 12px;
}

a {
    color: #1a73e8;
    font-weight: 500;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* ===== Better text readability ===== */
.article-card p {
    line-height: 1.5;
}

/* ===== Blue success box ===== */
div[data-testid="stAlert"][role="alert"] {
    background-color: #e6f0ff !important;
    color: #1a3d7c !important;
    border: 1px solid #cce0ff !important;
}

div[data-testid="stAlert"] p {
    color: #1a3d7c !important;
}

/* ===== Source buttons only ===== */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
    border-radius: 10px !important;
    text-align: left;
    padding: 8px 10px !important;
}

/* Unselected */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #ffffff !important;
    color: #374151 !important;
    border: 1px solid #e5e7eb !important;
}

/* Selected */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
    background-color: #eef4ff !important;
    color: #1a3d7c !important;
    border: 1px solid #d6e4ff !important;
    border-left: 4px solid #4a7cff !important;
    font-weight: 600 !important;
}

/* ===== Hover ===== */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
    background-color: #f5f7fb !important;
    border-color: #bfc8d8 !important;
}

/* ===== Selected row enhancement ===== */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"] {
    background-color: #eef4ff !important;
    color: #1a3d7c !important;
    border: 1px solid #d6e4ff !important;
    border-left: 4px solid #4a7cff !important;
    font-weight: 600 !important;
}

</style>
""", unsafe_allow_html=True)

# ================== DATA ==================
FEEDS_FILE = "saved_feeds.json"

def github_persistence_enabled():
    try:
        return all(
            key in st.secrets
            for key in ["GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO", "GITHUB_FEEDS_PATH"]
        )
    except Exception:
        return False

def load_feeds():
    if github_persistence_enabled():
        owner = st.secrets["GITHUB_OWNER"]
        repo = st.secrets["GITHUB_REPO"]
        path = st.secrets["GITHUB_FEEDS_PATH"]
        token = st.secrets["GITHUB_TOKEN"]

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content)

        except Exception as e:
            st.warning(f"Could not load feeds from GitHub. Falling back to local file. ({e})")

    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, "r") as f:
            return json.load(f)

    return []

def save_feeds(feed_list):
    if github_persistence_enabled():
        owner = st.secrets["GITHUB_OWNER"]
        repo = st.secrets["GITHUB_REPO"]
        path = st.secrets["GITHUB_FEEDS_PATH"]
        token = st.secrets["GITHUB_TOKEN"]

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            sha = None
            current_response = requests.get(url, headers=headers, timeout=15)

            if current_response.status_code == 200:
                current_data = current_response.json()
                sha = current_data.get("sha")

            encoded_content = base64.b64encode(
                json.dumps(feed_list, indent=2).encode("utf-8")
            ).decode("utf-8")

            payload = {
                "message": "Update saved feeds from Streamlit app",
                "content": encoded_content,
            }

            if sha:
                payload["sha"] = sha

            put_response = requests.put(url, headers=headers, json=payload, timeout=15)
            put_response.raise_for_status()
            return

        except Exception as e:
            st.error(f"Could not save feeds to GitHub. ({e})")
            return

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

if "selected_feeds" not in st.session_state:
    st.session_state.selected_feeds = {
        feed.get("url", ""): True for feed in all_feeds
    }

c_select, c_clear = st.sidebar.columns(2)

with c_select:
    if st.button("All", use_container_width=True):
        for url in st.session_state.selected_feeds:
            st.session_state.selected_feeds[url] = True
        st.rerun()

with c_clear:
    if st.button("None", use_container_width=True):
        for url in st.session_state.selected_feeds:
            st.session_state.selected_feeds[url] = False
        st.rerun()

st.sidebar.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

selected_urls = []

for i, feed in enumerate(all_feeds):
    feed_name = feed.get("name", "Unnamed Feed")
    feed_url = feed.get("url", "")

    if feed_url not in st.session_state.selected_feeds:
        st.session_state.selected_feeds[feed_url] = True

    c1, c2 = st.sidebar.columns([5, 1])

    is_selected = st.session_state.selected_feeds[feed_url]
    button_type = "primary" if is_selected else "secondary"

    with c1:
        button_label = feed_name

        if st.button(
            button_label,
            key=f"src_btn_{feed_url}",
            use_container_width=True,
            type=button_type
        ):
            st.session_state.selected_feeds[feed_url] = not st.session_state.selected_feeds[feed_url]
            st.rerun()

    with c2:
        if st.button("X", key=f"delete_{i}"):
            updated_feeds = [f for f in all_feeds if f.get("url") != feed_url]
            save_feeds(updated_feeds)
            if feed_url in st.session_state.selected_feeds:
                del st.session_state.selected_feeds[feed_url]
            st.rerun()

    if st.session_state.selected_feeds.get(feed_url, False):
        selected_urls.append(feed_url)

st.sidebar.header("Add New RSS Feed")

with st.sidebar.form("add_feed_form", clear_on_submit=True):
    new_feed_name = st.text_input("Feed name (e.g. Wired)")
    new_feed_url = st.text_input("Feed URL")
    save_feed_clicked = st.form_submit_button("Save Feed")

if save_feed_clicked:
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
article_limit = st.sidebar.slider("Articles per source", 5, 50, 20)

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

                for entry in parsed_feed.entries[:article_limit]:
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
