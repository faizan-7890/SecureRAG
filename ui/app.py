"""SecureRAG — Streamlit Chat Interface.

Launch with:
    streamlit run ui/app.py
"""

import json
import uuid

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SecureRAG",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — premium dark-theme styling
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
/* ── Global overrides ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    border-right: 1px solid rgba(99, 102, 241, 0.15);
}
section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #e2e8f0;
}

/* ── Health badge ── */
.health-ok {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 14px; border-radius: 999px;
    font-size: 0.82rem; font-weight: 600;
    background: rgba(34, 197, 94, 0.12); color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.25);
}
.health-err {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 14px; border-radius: 999px;
    font-size: 0.82rem; font-weight: 600;
    background: rgba(239, 68, 68, 0.12); color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.25);
}

/* ── Source card ── */
.source-card {
    background: rgba(99, 102, 241, 0.06);
    border: 1px solid rgba(99, 102, 241, 0.18);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    transition: border-color 0.2s ease;
}
.source-card:hover {
    border-color: rgba(99, 102, 241, 0.45);
}
.source-card .source-title {
    font-weight: 600; font-size: 0.88rem; color: #a5b4fc; margin-bottom: 6px;
}
.source-card .source-excerpt {
    font-size: 0.82rem; color: #94a3b8; line-height: 1.5;
}
.source-card .source-meta {
    font-size: 0.75rem; color: #64748b; margin-top: 6px;
}

/* ── Chat styling tweaks ── */
.stChatMessage {
    border-radius: 12px !important;
}

/* ── Token badge ── */
.token-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 500;
    background: rgba(99, 102, 241, 0.12); color: #818cf8;
    border: 1px solid rgba(99, 102, 241, 0.25);
    margin-bottom: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session-state defaults
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, object] = {
    "api_url": "http://127.0.0.1:8000",
    "openai_api_key": "",
    "token": None,
    "username": None,
    "messages": [],
    "session_id": uuid.uuid4().hex,
}
for key, value in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helper: API request wrapper
# ---------------------------------------------------------------------------

def _headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    api_key = (st.session_state.get("openai_api_key") or "").strip()
    if api_key:
        if api_key.startswith("AIzaSy"):
            headers["X-Gemini-API-Key"] = api_key
        else:
            headers["X-OpenAI-API-Key"] = api_key
    return headers


def _api(method: str, path: str, **kwargs) -> requests.Response | None:
    """Fire an HTTP request to the FastAPI backend, handling connection errors."""
    url = f"{st.session_state.api_url.rstrip('/')}{path}"
    try:
        return requests.request(method, url, headers=_headers(), timeout=120, **kwargs)
    except requests.ConnectionError:
        st.error("❌ Cannot reach the API server. Is it running?")
        return None
    except requests.Timeout:
        st.error("⏱️ Request timed out.")
        return None


def _stream_sse(payload: dict):
    """Stream SSE response from /chat/stream, yielding tokens and populating sources."""
    url = f"{st.session_state.api_url.rstrip('/')}/chat/stream"
    headers = dict(_headers())
    headers["Accept"] = "text/event-stream"

    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
            if resp.status_code != 200:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("detail", err_text)
                except Exception:
                    pass
                yield f"⚠️ Error: {err_text}", []
                return

            current_event = None
            sources: list[dict] = []

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    current_event = None
                    continue

                if raw_line.startswith("event:"):
                    current_event = raw_line.split(":", 1)[1].strip()
                elif raw_line.startswith("data:"):
                    data_str = raw_line.split(":", 1)[1].strip()
                    try:
                        data = json.loads(data_str)
                    except Exception:
                        data = {}

                    if current_event == "sources":
                        sources = data.get("sources", [])
                    elif current_event == "token":
                        token_text = data.get("token", "")
                        if token_text:
                            yield token_text, sources
                    elif current_event == "error":
                        err_msg = data.get("error", "Unknown error")
                        yield f"\n⚠️ {err_msg}", sources
                    elif current_event == "done":
                        break
    except requests.ConnectionError:
        yield "❌ Cannot reach the API server. Is it running?", []
    except requests.Timeout:
        yield "⏱️ Request timed out.", []
    except Exception as exc:
        yield f"⚠️ Stream failed: {exc}", []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("# 🔒 SecureRAG")
    st.caption("Retrieval-Augmented Generation over private documents")

    st.divider()

    # ── API Connection ──
    st.markdown("### ⚡ Connection")
    api_url = st.text_input(
        "API URL",
        value=st.session_state.api_url,
        placeholder="http://127.0.0.1:8000",
        label_visibility="collapsed",
    )
    st.session_state.api_url = api_url

    # Health check
    resp = _api("GET", "/health")
    if resp and resp.status_code == 200:
        st.markdown('<span class="health-ok">● Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="health-err">● Disconnected</span>', unsafe_allow_html=True)

    llm_key_input = st.text_input(
        "LLM API Key (OpenAI / Gemini)",
        value=st.session_state.openai_api_key,
        type="password",
        placeholder="sk-... or AIzaSy... (or set in .env)",
        help="Optional: Supply your OpenAI or Google Gemini API key directly without restarting.",
    )
    st.session_state.openai_api_key = llm_key_input

    st.divider()

    # ── Authentication ──
    st.markdown("### 🔑 Authentication")

    if st.session_state.token:
        st.markdown(
            f'<span class="token-badge">👤 {st.session_state.username}</span>',
            unsafe_allow_html=True,
        )
        if st.button("Log out", use_container_width=True):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()
    else:
        auth_tab_login, auth_tab_register = st.tabs(["Login", "Register"])

        with auth_tab_login:
            with st.form("login_form"):
                login_user = st.text_input("Username", key="login_user")
                login_pass = st.text_input("Password", type="password", key="login_pass")
                if st.form_submit_button("Login", use_container_width=True):
                    if login_user and login_pass:
                        resp = _api("POST", "/auth/login", json={"username": login_user, "password": login_pass})
                        if resp and resp.status_code == 200:
                            st.session_state.token = resp.json()["access_token"]
                            st.session_state.username = login_user
                            st.rerun()
                        elif resp:
                            st.error(resp.json().get("detail", "Login failed."))
                    else:
                        st.warning("Enter username and password.")

        with auth_tab_register:
            with st.form("register_form"):
                reg_user = st.text_input("Username", key="reg_user")
                reg_pass = st.text_input("Password", type="password", key="reg_pass")
                if st.form_submit_button("Register", use_container_width=True):
                    if reg_user and reg_pass:
                        resp = _api("POST", "/auth/register", json={"username": reg_user, "password": reg_pass})
                        if resp and resp.status_code == 201:
                            st.session_state.token = resp.json()["access_token"]
                            st.session_state.username = reg_user
                            st.success("Account created!")
                            st.rerun()
                        elif resp:
                            st.error(resp.json().get("detail", "Registration failed."))
                    else:
                        st.warning("Enter username and password.")

    st.divider()

    # ── Document Upload ──
    st.markdown("### 📄 Upload Document")
    uploaded_file = st.file_uploader(
        "Upload a document",
        type=["pdf", "txt", "md", "markdown"],
        label_visibility="collapsed",
        help="Supported: PDF, TXT, Markdown",
    )
    if uploaded_file is not None:
        if st.button("⬆️ Ingest", use_container_width=True):
            with st.spinner("Uploading and ingesting…"):
                resp = _api(
                    "POST",
                    "/documents/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")},
                )
                if resp and resp.status_code == 201:
                    data = resp.json()
                    st.success(f"✅ **{data['filename']}** ingested — {data['chunks']} chunks created.")
                elif resp:
                    st.error(resp.json().get("detail", "Upload failed."))

    st.divider()

    # ── Search & Streaming Strategy ──
    st.markdown("### 🔀 Search & Generation")
    streaming_enabled = st.toggle(
        "Real-Time Token Streaming (SSE)",
        value=True,
        help="Stream tokens live via Server-Sent Events as they are generated by OpenAI.",
    )
    hybrid_search_enabled = st.toggle(
        "Hybrid Search (BM25 + Vector)",
        value=True,
        help="Combine dense semantic vector search with sparse BM25 keyword matching via Reciprocal Rank Fusion (RRF).",
    )
    query_expansion_enabled = st.toggle(
        "Multi-Query Expansion",
        value=False,
        help="Use LLM to formulate complementary sub-queries for richer retrieval on complex questions.",
    )

    st.divider()

    # ── Clear conversation ──
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = uuid.uuid4().hex
        st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style='text-align:center; padding: 1.5rem 0 0.5rem;'>
        <h1 style='font-size: 2rem; font-weight: 700;
                   background: linear-gradient(135deg, #818cf8, #6366f1, #a78bfa);
                   -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
            SecureRAG Chat
        </h1>
        <p style='color: #94a3b8; font-size: 0.95rem;'>
            Ask questions about your uploaded documents
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Render message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("sources"):
            with st.expander(f"📚 {len(msg['sources'])} source(s)", expanded=False):
                for src in msg["sources"]:
                    page_info = f" · Page {src['page']}" if src.get("page") else ""
                    chunk_info = f" · Chunk {src['chunk_index']}" if src.get("chunk_index") is not None else ""
                    score_info = f" · Score {src['relevance_score']:.3f}" if src.get("relevance_score") is not None else ""
                    st.markdown(
                        f"""<div class="source-card">
                            <div class="source-title">📄 {src['filename']}</div>
                            <div class="source-excerpt">{src['excerpt']}</div>
                            <div class="source-meta">{page_info}{chunk_info}{score_info}</div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

# Chat input
if prompt := st.chat_input("Ask a question about your documents…"):
    # Display user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build dialogue history for conversational memory
    history_payload = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
        if m.get("role") in {"user", "assistant"}
    ]

    payload = {
        "question": prompt,
        "history": history_payload,
        "session_id": st.session_state.get("session_id"),
        "hybrid_search": hybrid_search_enabled,
        "query_expansion": query_expansion_enabled,
    }

    # Call API
    with st.chat_message("assistant"):
        if streaming_enabled:
            sources_container = st.empty()
            captured_sources: list[dict] = []

            def _token_stream_generator():
                for token, sources in _stream_sse(payload):
                    if sources and not captured_sources:
                        captured_sources.extend(sources)
                    yield token

            answer = st.write_stream(_token_stream_generator)

            if captured_sources:
                with st.expander(f"📚 {len(captured_sources)} source(s)", expanded=False):
                    for src in captured_sources:
                        page_info = f" · Page {src['page']}" if src.get("page") else ""
                        chunk_info = f" · Chunk {src['chunk_index']}" if src.get("chunk_index") is not None else ""
                        score_info = f" · Score {src['relevance_score']:.3f}" if src.get("relevance_score") is not None else ""
                        st.markdown(
                            f"""<div class="source-card">
                                <div class="source-title">📄 {src['filename']}</div>
                                <div class="source-excerpt">{src['excerpt']}</div>
                                <div class="source-meta">{page_info}{chunk_info}{score_info}</div>
                            </div>""",
                            unsafe_allow_html=True,
                        )

            st.session_state.messages.append({"role": "assistant", "content": answer or "", "sources": captured_sources})
        else:
            with st.spinner("Thinking…"):
                resp = _api("POST", "/chat", json=payload)

            if resp and resp.status_code == 200:
                data = resp.json()
                answer = data["answer"]
                sources = data.get("sources", [])

                st.markdown(answer)
                if sources:
                    with st.expander(f"📚 {len(sources)} source(s)", expanded=False):
                        for src in sources:
                            page_info = f" · Page {src['page']}" if src.get("page") else ""
                            chunk_info = f" · Chunk {src['chunk_index']}" if src.get("chunk_index") is not None else ""
                            score_info = f" · Score {src['relevance_score']:.3f}" if src.get("relevance_score") is not None else ""
                            st.markdown(
                                f"""<div class="source-card">
                                    <div class="source-title">📄 {src['filename']}</div>
                                    <div class="source-excerpt">{src['excerpt']}</div>
                                    <div class="source-meta">{page_info}{chunk_info}{score_info}</div>
                                </div>""",
                                unsafe_allow_html=True,
                            )

                st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})
            elif resp:
                error_msg = resp.json().get("detail", "Something went wrong.")
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})
            else:
                st.session_state.messages.append({"role": "assistant", "content": "⚠️ Could not reach the API."})
