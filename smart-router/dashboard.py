import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Smart Model Router",
    page_icon="⚡",
    layout="wide"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px 24px;
        margin: 4px;
    }
    .metric-label {
        color: #94a3b8;
        font-size: 13px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #f1f5f9;
        font-size: 32px;
        font-weight: 700;
        line-height: 1;
    }
    .metric-delta-good { color: #22c55e; font-size: 13px; margin-top: 6px; }
    .metric-delta-bad  { color: #f59e0b; font-size: 13px; margin-top: 6px; }
    .section-title {
        color: #f1f5f9;
        font-size: 18px;
        font-weight: 600;
        margin: 24px 0 12px 0;
    }
    .projection-card {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border: 1px solid #22c55e44;
        border-left: 4px solid #22c55e;
        border-radius: 12px;
        padding: 20px 24px;
        margin: 4px;
    }
    .projection-label { color: #22c55e; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; }
    .projection-value { color: #f1f5f9; font-size: 28px; font-weight: 700; margin-top: 4px; }
    .projection-sub   { color: #64748b; font-size: 12px; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_conn():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

@st.cache_data(ttl=30)
def load_data():
    return pd.read_sql("""
        SELECT id, created_at, model_used, difficulty_tag,
               cost_usd, cost_saved_usd, latency_ms, escalated,
               input_tokens, output_tokens
        FROM requests ORDER BY created_at ASC
    """, get_conn())

@st.cache_data(ttl=30)
def load_stats():
    cur = get_conn().cursor()

    cur.execute("SELECT COUNT(*) FROM requests")
    total_requests = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM requests")
    total_cost = float(cur.fetchone()[0])

    cur.execute("SELECT COALESCE(SUM(cost_saved_usd), 0) FROM requests")
    total_saved = float(cur.fetchone()[0])

    cur.execute("""
        SELECT COALESCE(SUM(
            (input_tokens / 1000.0 * 0.005) + (output_tokens / 1000.0 * 0.015)
        ), 0)
        FROM requests
    """)
    total_if_gpt4o = float(cur.fetchone()[0])

    cur.execute("""
        SELECT ROUND(100.0 * SUM(CASE WHEN escalated THEN 1 ELSE 0 END) /
               NULLIF(COUNT(*), 0), 1) FROM requests
    """)
    escalation_rate = float(cur.fetchone()[0] or 0)

    cur.execute("""
        SELECT model_used, COUNT(*) as cnt
        FROM requests GROUP BY model_used
    """)
    model_counts = dict(cur.fetchall())
    cur.close()

    return {
        "total_requests":  total_requests,
        "total_cost":      total_cost,
        "total_saved":     total_saved,
        "total_if_gpt4o":  total_if_gpt4o,
        "escalation_rate": escalation_rate,
        "model_counts":    model_counts,
    }

# ── Load ──────────────────────────────────────────────────────────────────────

try:
    stats = load_stats()
    df    = load_data()
except Exception as e:
    st.error(f"DB connection failed: {e}")
    st.stop()

if df.empty:
    st.warning("No requests yet. Fire some prompts at the API.")
    st.stop()

# ── Projections ───────────────────────────────────────────────────────────────

savings_per_request   = stats["total_saved"] / max(stats["total_requests"], 1)
gpt4o_cost_per_req    = stats["total_if_gpt4o"] / max(stats["total_requests"], 1)
savings_pct           = (savings_per_request / gpt4o_cost_per_req * 100) if gpt4o_cost_per_req > 0 else 0
proj_10k              = savings_per_request * 10_000
proj_100k             = savings_per_request * 100_000
proj_1m               = savings_per_request * 1_000_000

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## ⚡ Smart Model Router")
st.caption("Routes every prompt to the cheapest capable model · Live dashboard · Refreshes every 30s")
st.divider()

# ── Section 1: Key Metrics ────────────────────────────────────────────────────

st.markdown('<div class="section-title">Performance Overview</div>', unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Requests</div>
        <div class="metric-value">{stats['total_requests']:,}</div>
        <div class="metric-delta-good">↑ All routed automatically</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Actual Spend</div>
        <div class="metric-value">${stats['total_cost']:.4f}</div>
        <div class="metric-delta-good">With smart routing</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Without Router</div>
        <div class="metric-value">${stats['total_if_gpt4o']:.4f}</div>
        <div class="metric-delta-bad">Always GPT-4o baseline</div>
    </div>""", unsafe_allow_html=True)

with c4:
    haiku_pct = round(stats['model_counts'].get('claude-haiku-4-5', 0) / max(stats['total_requests'], 1) * 100)
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Cheap Model Rate</div>
        <div class="metric-value">{haiku_pct}%</div>
        <div class="metric-delta-good">Routed to Haiku</div>
    </div>""", unsafe_allow_html=True)

with c5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Escalation Rate</div>
        <div class="metric-value">{stats['escalation_rate']}%</div>
        <div class="metric-delta-good">Self-healed automatically</div>
    </div>""", unsafe_allow_html=True)

# ── Section 2: Projected Savings ─────────────────────────────────────────────

st.markdown('<div class="section-title">Projected Savings at Scale</div>', unsafe_allow_html=True)
st.caption(f"Based on {savings_pct:.1f}% average cost reduction per request vs always using GPT-4o")

p1, p2, p3 = st.columns(3)

with p1:
    st.markdown(f"""
    <div class="projection-card">
        <div class="projection-label">At 10,000 requests/month</div>
        <div class="projection-value">${proj_10k:.2f} saved</div>
        <div class="projection-sub">vs. ${gpt4o_cost_per_req * 10000:.2f} always-GPT-4o spend</div>
    </div>""", unsafe_allow_html=True)

with p2:
    st.markdown(f"""
    <div class="projection-card">
        <div class="projection-label">At 100,000 requests/month</div>
        <div class="projection-value">${proj_100k:.2f} saved</div>
        <div class="projection-sub">vs. ${gpt4o_cost_per_req * 100000:.2f} always-GPT-4o spend</div>
    </div>""", unsafe_allow_html=True)

with p3:
    st.markdown(f"""
    <div class="projection-card">
        <div class="projection-label">At 1,000,000 requests/month</div>
        <div class="projection-value">${proj_1m:,.0f} saved</div>
        <div class="projection-sub">vs. ${gpt4o_cost_per_req * 1_000_000:,.0f} always-GPT-4o spend</div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ── Section 3: Charts ─────────────────────────────────────────────────────────

col_l, col_r = st.columns(2)

with col_l:
    st.markdown('<div class="section-title">Model Usage Distribution</div>', unsafe_allow_html=True)
    model_counts_df = pd.DataFrame(
        list(stats["model_counts"].items()),
        columns=["Model", "Requests"]
    )
    color_map = {
        "claude-haiku-4-5":  "#22c55e",
        "claude-sonnet-4-6": "#3b82f6",
        "gpt-4o":            "#f59e0b",
    }
    fig_pie = px.pie(
        model_counts_df,
        names="Model", values="Requests",
        color="Model", color_discrete_map=color_map,
        hole=0.5,
    )
    fig_pie.update_traces(textposition="outside", textinfo="percent+label")
    fig_pie.update_layout(
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8")
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_r:
    st.markdown('<div class="section-title">Cost by Model vs GPT-4o Equivalent</div>', unsafe_allow_html=True)

    model_agg = df.groupby("model_used").agg(
        actual=("cost_usd", "sum"),
        tokens=("input_tokens", "sum"),
        out_tokens=("output_tokens", "sum")
    ).reset_index()
    model_agg["gpt4o_equiv"] = (model_agg["tokens"] + model_agg["out_tokens"]) / 1000 * 0.005

    fig_compare = go.Figure()
    for _, row in model_agg.iterrows():
        color = color_map.get(row["model_used"], "#94a3b8")
        fig_compare.add_trace(go.Bar(
            name=row["model_used"],
            x=[row["model_used"]],
            y=[row["actual"]],
            marker_color=color,
            text=f'${row["actual"]:.5f}',
            textposition="outside"
        ))
        fig_compare.add_trace(go.Bar(
            name=f'{row["model_used"]} (GPT-4o equiv)',
            x=[row["model_used"]],
            y=[row["gpt4o_equiv"]],
            marker_color=color,
            opacity=0.3,
            text=f'${row["gpt4o_equiv"]:.5f}',
            textposition="outside",
            showlegend=False
        ))

    fig_compare.update_layout(
        barmode="group",
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
        yaxis=dict(gridcolor="#1e293b", title="Cost (USD)"),
        xaxis=dict(gridcolor="#1e293b")
    )
    st.plotly_chart(fig_compare, use_container_width=True)

st.divider()

# ── Section 4: Cost Savings Over Time ────────────────────────────────────────

st.markdown('<div class="section-title">Cumulative Cost Savings Over Time</div>', unsafe_allow_html=True)

df["created_at"] = pd.to_datetime(df["created_at"])
df["hour"] = df["created_at"].dt.floor("H")
time_data = df.groupby("hour").agg(
    actual=("cost_usd", "sum"),
    saved=("cost_saved_usd", "sum")
).reset_index()
time_data["cum_actual"] = time_data["actual"].cumsum()
time_data["cum_saved"]  = time_data["saved"].cumsum()
time_data["cum_gpt4o"]  = (time_data["actual"] + time_data["saved"]).cumsum()

fig_line = go.Figure()
fig_line.add_trace(go.Scatter(
    x=time_data["hour"], y=time_data["cum_gpt4o"],
    name="If Always GPT-4o", line=dict(color="#f59e0b", width=2, dash="dash"),
    fill=None
))
fig_line.add_trace(go.Scatter(
    x=time_data["hour"], y=time_data["cum_actual"],
    name="Actual Cost", line=dict(color="#3b82f6", width=2),
    fill="tonexty", fillcolor="rgba(34,197,94,0.1)"
))
fig_line.update_layout(
    margin=dict(t=10, b=10, l=10, r=10),
    height=260,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8"),
    yaxis=dict(gridcolor="#1e293b", title="Cumulative Cost (USD)"),
    xaxis=dict(gridcolor="#1e293b"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ── Section 5: Recent Requests ────────────────────────────────────────────────

st.markdown('<div class="section-title">Recent Requests</div>', unsafe_allow_html=True)

display_df = df.sort_values("created_at", ascending=False).head(20)[[
    "created_at", "model_used", "difficulty_tag",
    "cost_usd", "cost_saved_usd", "latency_ms", "escalated"
]].copy()
display_df.columns = ["Timestamp", "Model", "Difficulty", "Cost ($)", "Saved ($)", "Latency (ms)", "Escalated"]
display_df["Cost ($)"]  = display_df["Cost ($)"].apply(lambda x: f"${x:.6f}")
display_df["Saved ($)"] = display_df["Saved ($)"].apply(lambda x: f"${x:.6f}")
display_df["Escalated"] = display_df["Escalated"].apply(lambda x: "✅" if x else "—")
st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()
st.caption("PostgreSQL · Streamlit · Anthropic + OpenAI APIs · Auto-refreshes every 30s")