"""Smart Router Dashboard — metrics + live streaming chat."""
import os
import json
import time
import psycopg
import httpx
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(         
    page_title="Smart Router",
    page_icon="SR",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if not DATABASE_URL:
    st.error("DATABASE_URL environment variable is not set.")
    st.stop()

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────

st.markdown("""
<style>
  .stApp { background: #0f172a; color: #e2e8f0; }

  .metric-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
  }
  .metric-label { font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: .08em; }
  .metric-value { font-size: 32px; font-weight: 700; color: #f1f5f9; margin: 4px 0; }
  .metric-sub   { font-size: 13px; color: #64748b; }

  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .badge-simple    { background:#052e16; color:#22c55e; border:1px solid #22c55e44; }
  .badge-medium    { background:#172554; color:#3b82f6; border:1px solid #3b82f644; }
  .badge-complex   { background:#2e1065; color:#a855f7; border:1px solid #a855f744; }
  .badge-escalated { background:#431407; color:#fb923c; border:1px solid #fb923c44; }

  .chat-user {
    background: #1e40af;
    color: #e0f2fe;
    padding: 10px 16px;
    border-radius: 18px 18px 4px 18px;
    margin: 8px 0 4px auto;
    max-width: 70%;
    width: fit-content;
    float: right;
    clear: both;
    font-size: 14px;
  }
  .chat-assistant {
    background: #1e293b;
    color: #e2e8f0;
    padding: 10px 16px;
    border-radius: 18px 18px 18px 4px;
    margin: 4px auto 4px 0;
    max-width: 80%;
    width: fit-content;
    float: left;
    clear: both;
    font-size: 14px;
    white-space: pre-wrap;
  }
  .chat-meta {
    float: left; clear: both;
    margin: 2px 0 12px 4px;
    font-size: 11px; color: #64748b;
  }
  .routing-header {
    background: #0f1f11;
    border: 1px solid #166534;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    color: #86efac;
    margin: 6px 0;
    float: left; clear: both;
    width: fit-content;
  }
  .clearfix { clear: both; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_stats():
    conn = psycopg.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT COUNT(*),
               COALESCE(SUM(cost_usd),0),
               COALESCE(SUM(cost_saved_usd),0),
               COALESCE(AVG(escalated::int)*100,0)
        FROM requests
    """)
    row = cur.fetchone()
    cur.execute("SELECT model_used, COUNT(*) FROM requests GROUP BY model_used")
    model_rows = cur.fetchall()
    cur.execute("""
        SELECT DATE_TRUNC('hour', created_at) AS hr,
               SUM(cost_saved_usd) AS saved
        FROM requests GROUP BY hr ORDER BY hr
    """)
    savings_rows = cur.fetchall()
    cur.close(); conn.close()
    return {
        "total":      int(row[0]),
        "cost":       float(row[1]),
        "saved":      float(row[2]),
        "esc_pct":    float(row[3]),
        "model_dist": {r[0]: r[1] for r in model_rows},
        "savings_ts": savings_rows,
    }


@st.cache_data(ttl=30)
def load_recent():
    conn = psycopg.connect(DATABASE_URL)
    df = pd.read_sql("""
        SELECT created_at, difficulty_tag, model_used,
               cost_usd, cost_saved_usd, latency_ms, escalated
        FROM requests ORDER BY created_at DESC LIMIT 20
    """, conn)
    conn.close()
    return df


# ─────────────────────────────────────────────
# Streaming helper
# ─────────────────────────────────────────────

def stream_chat(prompt: str):
    """
    Yields dicts from the /v1/chat/stream endpoint:
      {"type": "metadata", "difficulty_tag": "...", "model_used": "..."}
      {"type": "token",    "text": "..."}
      {"type": "done",     "cost_usd": ..., "cost_saved_usd": ..., ...}
      {"type": "error",    "message": "..."}
    """
    url = f"{API_BASE_URL}/v1/chat/stream"
    with httpx.stream("POST", url, json={"prompt": prompt}, timeout=120) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ─────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────

tab_dash, tab_chat = st.tabs(["Dashboard", "Try It Live"])


# ══════════════════════════════════════════════
# TAB 1  Dashboard
# ══════════════════════════════════════════════

with tab_dash:
    st.markdown("## Smart Router — Metrics")

    db_ok = True
    stats = None
    df    = None

    try:
        stats = load_stats()
        df    = load_recent()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.info("Run `python3 -m app.database` to initialise the schema, then send prompts via the **Try It Live** tab.")
        db_ok = False

    if db_ok and stats and stats["total"] == 0:
        st.warning("No requests yet — try the **Try It Live** tab first.")
        db_ok = False

    if db_ok and stats:
        gpt4o_equiv = stats["cost"] + stats["saved"]
        savings_pct = (stats["saved"] / gpt4o_equiv * 100) if gpt4o_equiv > 0 else 0

        c1, c2, c3, c4 = st.columns(4)
        for col, label, value, sub in [
            (c1, "Total Requests",  f"{stats['total']:,}",       "all time"),
            (c2, "Actual Spend",    f"${stats['cost']:.4f}",     "real cost"),
            (c3, "Cost Saved",      f"${stats['saved']:.4f}",    f"{savings_pct:.0f}% vs GPT-4o baseline"),
            (c4, "Escalation Rate", f"{stats['esc_pct']:.1f}%",  "of requests"),
        ]:
            with col:
                st.markdown(f"""
                <div class="metric-card">
                  <div class="metric-label">{label}</div>
                  <div class="metric-value">{value}</div>
                  <div class="metric-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("---")

        ch1, ch2 = st.columns(2)
        with ch1:
            if stats["model_dist"]:
                fig = px.pie(
                    values=list(stats["model_dist"].values()),
                    names=list(stats["model_dist"].keys()),
                    title="Model Distribution",
                    color_discrete_sequence=["#22c55e", "#3b82f6", "#a855f7"],
                )
                fig.update_layout(paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
                                  font_color="#e2e8f0", title_font_color="#f1f5f9")
                st.plotly_chart(fig, use_container_width=True)

        with ch2:
            if stats["savings_ts"]:
                ts = pd.DataFrame(stats["savings_ts"], columns=["hour", "saved"])
                ts["cumulative_saved"] = ts["saved"].cumsum()
                fig2 = px.area(ts, x="hour", y="cumulative_saved",
                               title="Cumulative Savings",
                               labels={"cumulative_saved": "$ Saved", "hour": ""},
                               color_discrete_sequence=["#22c55e"])
                fig2.update_layout(paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
                                   font_color="#e2e8f0", title_font_color="#f1f5f9")
                st.plotly_chart(fig2, use_container_width=True)

        if stats["total"] > 0:
            st.markdown("### Savings Projections")
            avg_saved = stats["saved"] / stats["total"]
            p1, p2, p3 = st.columns(3)
            for col, volume in zip([p1, p2, p3], [10_000, 100_000, 1_000_000]):
                proj = avg_saved * volume
                with col:
                    st.markdown(f"""
                    <div class="metric-card">
                      <div class="metric-label">{volume:,} req/month</div>
                      <div class="metric-value">${proj:,.0f}</div>
                      <div class="metric-sub">projected monthly savings</div>
                    </div>""", unsafe_allow_html=True)

        if df is not None and not df.empty:
            st.markdown("---")
            st.markdown("### Recent Requests")
            st.dataframe(
                df.rename(columns={
                    "created_at":     "Time",
                    "difficulty_tag": "Tier",
                    "model_used":     "Model",
                    "cost_usd":       "Cost ($)",
                    "cost_saved_usd": "Saved ($)",
                    "latency_ms":     "Latency (ms)",
                    "escalated":      "Escalated",
                }),
                use_container_width=True,
                hide_index=True,
            )

    st.caption("Auto-refreshes every 30 s.")


# ══════════════════════════════════════════════
# TAB 2  Live Streaming Chat
# ══════════════════════════════════════════════

with tab_chat:
    st.markdown("## Try It Live")
    st.caption(
        "The routing decision appears **immediately** after classification. "
        "Tokens stream in as the model generates them."
    )

    # Manage input clearing via session state (must happen before widget instantiation)
    if "chat_input" not in st.session_state:
        st.session_state["chat_input"] = ""
    if st.session_state.get("clear_chat_input", False):
        st.session_state["chat_input"] = ""
        st.session_state["clear_chat_input"] = False

    # Top container for current Q&A (always above the input)
    chat_area = st.container()

    st.markdown("---")

    # Centered input in the middle of the page
    left, center, right = st.columns([1, 2, 1])
    with center:
        user_input = st.text_area(
            "Your prompt",
            placeholder="Ask anything — simple, medium, or complex…",
            height=80,
            label_visibility="collapsed",
            key="chat_input",
        )
        send = st.button("Send ▶", use_container_width=True, type="primary")

    # ── Handle send ───────────────────────────────────────────────────
    if send and user_input.strip():
        prompt = user_input.strip()

        # Mark for clearing the text input on the next run
        st.session_state["clear_chat_input"] = True

        # Render Q&A above the input
        with chat_area:
            st.markdown(
                f'<div class="chat-user">{prompt}</div>'
                '<div class="clearfix"></div>',
                unsafe_allow_html=True,
            )

            routing_ph  = st.empty()
            response_ph = st.empty()
            meta_ph     = st.empty()

        routing_ph.markdown(
            '<div class="routing-header">Classifying…</div>'
            '<div class="clearfix"></div>',
            unsafe_allow_html=True,
        )

        accumulated = ""
        metadata    = {}
        done_data   = {}
        error_msg   = None

        try:
            for frame in stream_chat(prompt):
                ftype = frame.get("type")

                if ftype == "metadata":
                    metadata  = frame
                    tag       = frame.get("difficulty_tag", "?")
                    model     = frame.get("model_used", "?")
                    badge_cls = f"badge-{tag}" if tag in ("simple","medium","complex") else "badge-medium"
                    routing_ph.markdown(
                        f'<div class="routing-header">'
                        f'<span class="badge {badge_cls}">{tag}</span>'
                        f'  →  <strong>{model}</strong> &nbsp; generating…'
                        f'</div><div class="clearfix"></div>',
                        unsafe_allow_html=True,
                    )

                elif ftype == "token":
                    accumulated += frame.get("text", "")
                    response_ph.markdown(
                        f'<div class="chat-assistant">{accumulated}▌</div>'
                        '<div class="clearfix"></div>',
                        unsafe_allow_html=True,
                    )

                elif ftype == "done":
                    done_data   = frame
                    escalated   = frame.get("escalated", False)
                    final_tag   = frame.get("difficulty_tag", metadata.get("difficulty_tag", ""))
                    final_model = frame.get("model_used",     metadata.get("model_used", ""))
                    cost        = frame.get("cost_usd", 0)
                    saved       = frame.get("cost_saved_usd", 0)
                    latency     = frame.get("latency_ms", 0)

                    badge_cls = f"badge-{final_tag}" if final_tag in ("simple","medium","complex") else "badge-medium"
                    esc_badge = ' <span class="badge badge-escalated">↑ escalated</span>' if escalated else ""

                    routing_ph.markdown(
                        f'<div class="routing-header">'
                        f'<span class="badge {badge_cls}">{final_tag}</span>{esc_badge}'
                        f'  →  <strong>{final_model}</strong>'
                        f'</div><div class="clearfix"></div>',
                        unsafe_allow_html=True,
                    )
                    # Remove streaming cursor
                    response_ph.markdown(
                        f'<div class="chat-assistant">{accumulated}</div>'
                        '<div class="clearfix"></div>',
                        unsafe_allow_html=True,
                    )
                    meta_ph.markdown(
                        f'<div class="chat-meta">'
                        f'${cost:.6f} &nbsp;·&nbsp; '
                        f'${saved:.6f} saved &nbsp;·&nbsp; '
                        f'{latency} ms'
                        f'</div><div class="clearfix"></div>',
                        unsafe_allow_html=True,
                    )

                elif ftype == "error":
                    error_msg = frame.get("message", "Unknown error")
                    break

        except Exception as e:
            error_msg = str(e)

        if error_msg:
            routing_ph.error(f"{error_msg}")