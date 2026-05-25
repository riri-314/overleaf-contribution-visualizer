"""Build interactive Plotly chart figures from parsed Overleaf data."""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data import DAY_ORDER

_LAYOUT_DEFAULTS = dict(
    font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=60, r=20, t=50, b=50),
    hoverlabel=dict(bgcolor="white", font_size=12),
)


def _apply(fig: go.Figure, **overrides) -> go.Figure:
    fig.update_layout(**{**_LAYOUT_DEFAULTS, **overrides})
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0", zeroline=False)
    return fig


# ── Overview ──────────────────────────────────────────────────────────────────

def chart_words_overview(df, colors, user_labels):
    fig = go.Figure()
    for name in user_labels:
        sub = df[df["name"] == name]
        color = colors.get(name, "#888")
        fig.add_trace(go.Bar(
            name=name,
            x=["Words inserted", "Words deleted"],
            y=[sub["words_ins"].sum(), sub["words_del"].sum()],
            marker_color=color,
            hovertemplate="%{x}: <b>%{y:,}</b><extra>" + name + "</extra>",
        ))
    return _apply(fig,
        title="Words Inserted & Deleted",
        barmode="group",
        yaxis_tickformat=",",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
    )


def chart_share_pie(df, colors, user_labels):
    totals = df.groupby("name")["words_ins"].sum().reindex(user_labels, fill_value=0)
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(),
        values=totals.values.tolist(),
        marker_colors=[colors.get(n, "#888") for n in totals.index],
        hole=0.45,
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value:,} words (%{percent})<extra></extra>",
    ))
    return _apply(fig, title="Share of Words Written", showlegend=False, margin=dict(l=20, r=20, t=50, b=20))


def chart_cumulative(df, colors, colors_rgba, user_labels):
    fig = go.Figure()
    for name in user_labels:
        sub = df[df["name"] == name].sort_values("start")
        cum = sub.groupby("start")["words_ins"].sum().cumsum()
        color = colors.get(name, "#888")
        fig.add_trace(go.Scatter(
            x=cum.index.tolist(),
            y=cum.values.tolist(),
            mode="lines",
            name=name,
            line=dict(color=color, width=2.5),
            fill="tozeroy",
            fillcolor=colors_rgba.get(name, "rgba(0,0,0,0.05)"),
            hovertemplate="%{x|%d %b %Y}<br><b>%{y:,} words</b><extra>" + name + "</extra>",
        ))
    return _apply(fig,
        title="Cumulative Words Over Time",
        xaxis_title="Date",
        yaxis_title="Cumulative words",
        yaxis_tickformat=",",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
    )


# ── Timeline ──────────────────────────────────────────────────────────────────

def chart_daily_intensity(df, colors, user_labels):
    all_days = pd.date_range(df["day"].min(), df["day"].max(), freq="D")
    fig = make_subplots(rows=len(user_labels), cols=1, shared_xaxes=True,
                        vertical_spacing=0.06,
                        subplot_titles=user_labels)
    for i, name in enumerate(user_labels, start=1):
        sub = df[df["name"] == name].groupby("day")["words_ins"].sum().reindex(all_days, fill_value=0)
        color = colors.get(name, "#888")
        fig.add_trace(go.Bar(
            x=sub.index.tolist(),
            y=sub.values.tolist(),
            marker_color=color,
            name=name,
            showlegend=False,
            hovertemplate="%{x|%d %b %Y}<br><b>%{y:,} words</b><extra>" + name + "</extra>",
        ), row=i, col=1)
        fig.update_yaxes(tickformat=",", row=i, col=1)

    return _apply(fig,
        title="Daily Writing Intensity",
        hovermode="x unified",
        height=max(300, 220 * len(user_labels)),
    )


def chart_session_timeline(sdf, colors, user_labels):
    fig = make_subplots(rows=len(user_labels), cols=1, shared_xaxes=True,
                        vertical_spacing=0.06,
                        subplot_titles=user_labels)
    for i, name in enumerate(user_labels, start=1):
        sub = sdf[sdf["name"] == name]
        color = colors.get(name, "#888")
        fig.add_trace(go.Scatter(
            x=sub["start"].tolist(),
            y=sub["jitter"].tolist(),
            mode="markers",
            name=name,
            showlegend=False,
            marker=dict(color=color, size=8, opacity=0.65, line=dict(width=0)),
            hovertemplate="%{x|%d %b %Y, %H:%M}<extra>" + name + "</extra>",
        ), row=i, col=1)
        fig.update_yaxes(showticklabels=False, showgrid=False, zeroline=True,
                         zerolinecolor="#ddd", row=i, col=1)

    return _apply(fig,
        title="Session Timeline",
        hovermode="closest",
        height=max(250, 170 * len(user_labels)),
    )


# ── Patterns ──────────────────────────────────────────────────────────────────

def chart_sessions_heatmap(sdf):
    pivot = sdf.groupby(["weekday", "hour"]).size().unstack(fill_value=0)
    pivot = pivot.reindex([d for d in DAY_ORDER if d in pivot.index])
    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=[f"{h:02d}h" for h in pivot.columns.tolist()],
        y=pivot.index.tolist(),
        colorscale="YlOrRd",
        text=pivot.values.tolist(),
        texttemplate="%{text}",
        hovertemplate="<b>%{y}, %{x}</b><br>%{z} sessions<extra></extra>",
        colorbar=dict(title="sessions"),
    ))
    return _apply(fig,
        title="Sessions by Hour & Weekday",
        xaxis_title="Hour of day",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
    )


def chart_sessions_per_week(sdf, colors, user_labels):
    weekly = sdf.groupby(["week", "name"]).size().unstack(fill_value=0)
    fig = go.Figure()
    for name in user_labels:
        if name not in weekly.columns:
            continue
        fig.add_trace(go.Bar(
            x=[str(d.date()) for d in weekly.index],
            y=weekly[name].values.tolist(),
            name=name,
            marker_color=colors.get(name, "#888"),
            hovertemplate="Week of %{x}<br><b>%{y} sessions</b><extra>" + name + "</extra>",
        ))
    return _apply(fig,
        title="Sessions per Week",
        barmode="group",
        xaxis_title="Week",
        yaxis_title="Sessions",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
    )


def chart_ins_vs_del(df, colors, user_labels):
    fig = go.Figure()
    for name in user_labels:
        sub = df[(df["name"] == name) & (df["chapter"]) &
                 ((df["words_ins"] > 0) | (df["words_del"] > 0))]
        fig.add_trace(go.Scatter(
            x=sub["words_ins"].tolist(),
            y=sub["words_del"].tolist(),
            mode="markers",
            name=name,
            marker=dict(color=colors.get(name, "#888"), size=7, opacity=0.6,
                        line=dict(width=0.5, color="white")),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Inserted: %{x:,}<br>"
                "Deleted: %{y:,}<extra>" + name + "</extra>"
            ),
            text=sub["file"].tolist(),
        ))
    max_v = max(df["words_ins"].max(), df["words_del"].max()) * 1.05
    fig.add_trace(go.Scatter(
        x=[0, max_v], y=[0, max_v],
        mode="lines",
        line=dict(dash="dash", color="#aaa", width=1),
        name="ins = del",
        hoverinfo="skip",
    ))
    return _apply(fig,
        title="Insertions vs. Deletions (chapter files)",
        xaxis_title="Words inserted",
        yaxis_title="Words deleted",
        xaxis_tickformat=",",
        yaxis_tickformat=",",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
    )


# ── Chapters ──────────────────────────────────────────────────────────────────

def chart_top_chapters(df, colors, user_labels):
    chap = df[df["chapter"]]
    if chap.empty:
        return None
    fp = chap.groupby(["file", "name"])["words_ins"].sum().unstack(fill_value=0)
    for name in user_labels:
        if name not in fp.columns:
            fp[name] = 0
    fp["total"] = fp[user_labels].sum(axis=1)
    top = fp.nlargest(20, "total").drop(columns="total")

    fig = go.Figure()
    for name in user_labels:
        if name not in top.columns:
            continue
        fig.add_trace(go.Bar(
            y=top.index.tolist(),
            x=top[name].values.tolist(),
            name=name,
            orientation="h",
            marker_color=colors.get(name, "#888"),
            hovertemplate="%{y}<br><b>%{x:,} words</b><extra>" + name + "</extra>",
        ))
    return _apply(fig,
        title="Top 20 Chapters by Words Inserted",
        barmode="stack",
        xaxis_title="Words inserted",
        xaxis_tickformat=",",
        yaxis=dict(autorange="reversed", showgrid=False),
        legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
        height=550,
    )


def chart_chapter_ownership(df, colors, user_labels):
    chap = df[df["chapter"]]
    if chap.empty:
        return None
    pct = chap.groupby(["file", "name"])["words_ins"].sum().unstack(fill_value=0)
    for name in user_labels:
        if name not in pct.columns:
            pct[name] = 0
    pct["total"] = pct[user_labels].sum(axis=1)
    pct = pct[pct["total"] > 50]
    for name in user_labels:
        pct[name] = (pct[name] / pct["total"] * 100).round(1)
    pct = pct[user_labels].sort_values(user_labels[0], ascending=True)

    fig = go.Figure(go.Heatmap(
        z=pct.values.tolist(),
        x=pct.columns.tolist(),
        y=pct.index.tolist(),
        colorscale="RdYlBu_r",
        zmin=0, zmax=100,
        text=[[f"{v:.0f}%" for v in row] for row in pct.values.tolist()],
        texttemplate="%{text}",
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}%<extra></extra>",
        colorbar=dict(title="% words"),
    ))
    return _apply(fig,
        title="Chapter Ownership (% words per author)",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
        height=max(320, len(pct) * 28 + 80),
    )


def chart_chapter_scatter(df, colors, user_labels):
    if len(user_labels) < 2:
        return None
    chap = df[df["chapter"]]
    if chap.empty:
        return None
    u1, u2 = user_labels[0], user_labels[1]
    fp = chap.groupby(["file", "name"])["words_ins"].sum().unstack(fill_value=0)
    for name in [u1, u2]:
        if name not in fp.columns:
            fp[name] = 0
    fp = fp[(fp[[u1, u2]] > 0).any(axis=1)]
    total_w = fp[u1] + fp[u2]
    sizes = (10 + 45 * (total_w / total_w.max())).tolist() if total_w.max() > 0 else [10] * len(fp)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fp[u1].tolist(),
        y=fp[u2].tolist(),
        mode="markers+text",
        text=fp.index.tolist(),
        textposition="top right",
        textfont=dict(size=9, color="#555"),
        marker=dict(size=sizes, color="#7B9CC9", opacity=0.75,
                    line=dict(color="#3a5f8a", width=1)),
        hovertemplate=(
            "<b>%{text}</b><br>"
            + u1 + ": %{x:,}<br>"
            + u2 + ": %{y:,}<extra></extra>"
        ),
        name="chapters",
    ))
    max_v = max(fp[u1].max(), fp[u2].max()) * 1.1
    fig.add_trace(go.Scatter(
        x=[0, max_v], y=[0, max_v],
        mode="lines",
        line=dict(dash="dash", color="#aaa", width=1),
        name="equal split",
        hoverinfo="skip",
    ))
    return _apply(fig,
        title="Per-Chapter Word Split (bubble = total words)",
        xaxis_title=f"Words by {u1}",
        yaxis_title=f"Words by {u2}",
        xaxis_tickformat=",",
        yaxis_tickformat=",",
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
    )


# ── Aggregator ────────────────────────────────────────────────────────────────

def build_all_charts(data: dict) -> dict:
    df          = data["df"]
    sdf         = data["sdf"]
    colors      = data["colors"]
    colors_rgba = data["colors_rgba"]
    user_labels = data["user_labels"]

    builders = {
        "words_overview":    lambda: chart_words_overview(df, colors, user_labels),
        "share_pie":         lambda: chart_share_pie(df, colors, user_labels),
        "cumulative":        lambda: chart_cumulative(df, colors, colors_rgba, user_labels),
        "daily_intensity":   lambda: chart_daily_intensity(df, colors, user_labels),
        "session_timeline":  lambda: chart_session_timeline(sdf, colors, user_labels),
        "sessions_heatmap":  lambda: chart_sessions_heatmap(sdf),
        "sessions_per_week": lambda: chart_sessions_per_week(sdf, colors, user_labels),
        "ins_vs_del":        lambda: chart_ins_vs_del(df, colors, user_labels),
        "top_chapters":      lambda: chart_top_chapters(df, colors, user_labels),
        "chapter_ownership": lambda: chart_chapter_ownership(df, colors, user_labels),
        "chapter_scatter":   lambda: chart_chapter_scatter(df, colors, user_labels),
    }

    result = {}
    for chart_id, fn in builders.items():
        fig = fn()
        if fig is not None:
            result[chart_id] = fig.to_json()
    return result
