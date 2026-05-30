"""Build interactive Plotly chart figures from parsed Overleaf data."""
import pandas as pd
import plotly.graph_objects as go

from data import DAY_ORDER

MAX_CHART_CONTRIBUTORS = 8
OTHER_CONTRIBUTORS = "Other contributors"
OTHER_COLOR = "#718096"
_DISPLAY_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
]

_LAYOUT_DEFAULTS = dict(
    font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", size=12),
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=60, r=20, t=50, b=50),
    hoverlabel=dict(
        bgcolor="white",
        bordercolor="#e2e8f0",
        font=dict(color="#1a202c", size=12),
    ),
    autosize=True,  # fill container div; height is controlled by CSS
)


def _apply(fig: go.Figure, **overrides) -> go.Figure:
    fig.update_layout(**{**_LAYOUT_DEFAULTS, **overrides})
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0", zeroline=False)
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 0.12) -> str:
    if not hex_color.startswith("#") or len(hex_color) != 7:
        return f"rgba(113,128,150,{alpha})"
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _name_margin(user_labels) -> int:
    longest = max((len(name) for name in user_labels), default=0)
    return min(220, max(90, longest * 7))


def _visible_contributors(df, sdf, user_labels):
    names = list(dict.fromkeys([
        *user_labels,
        *df.get("name", pd.Series(dtype=str)).dropna().tolist(),
        *sdf.get("name", pd.Series(dtype=str)).dropna().tolist(),
    ]))
    if not names:
        return []

    stats = pd.DataFrame(index=pd.Index(names, name="name"))
    word_totals = df.groupby("name")[["words_ins", "words_del"]].sum()
    stats["activity"] = (
        word_totals.sum(axis=1).reindex(stats.index, fill_value=0)
        if not word_totals.empty
        else 0
    )
    session_counts = sdf.groupby("name").size() if not sdf.empty else pd.Series(dtype=int)
    stats["sessions"] = session_counts.reindex(stats.index, fill_value=0)
    stats["original_order"] = range(len(stats))
    stats = stats[(stats["activity"] > 0) | (stats["sessions"] > 0)]

    return stats.sort_values(
        ["activity", "sessions", "original_order"],
        ascending=[False, False, True],
    ).index.tolist()


def _prepare_chart_data(df, sdf, user_labels, colors, colors_rgba):
    ordered = _visible_contributors(df, sdf, user_labels)
    keep = ordered[:MAX_CHART_CONTRIBUTORS]
    grouped = len(ordered) > len(keep)
    display_labels = keep + ([OTHER_CONTRIBUTORS] if grouped else [])

    display_df = df.copy()
    display_sdf = sdf.copy()
    if grouped:
        display_df.loc[~display_df["name"].isin(keep), "name"] = OTHER_CONTRIBUTORS
        display_sdf.loc[~display_sdf["name"].isin(keep), "name"] = OTHER_CONTRIBUTORS

    display_colors = {}
    display_colors_rgba = {}
    for i, name in enumerate(display_labels):
        color = (
            OTHER_COLOR
            if name == OTHER_CONTRIBUTORS
            else colors.get(name, _DISPLAY_PALETTE[i % len(_DISPLAY_PALETTE)])
        )
        display_colors[name] = color
        display_colors_rgba[name] = colors_rgba.get(name, _hex_to_rgba(color))

    return display_df, display_sdf, display_labels, display_colors, display_colors_rgba


# ── Overview ──────────────────────────────────────────────────────────────────

def chart_words_overview(df, colors, user_labels):
    totals = df.groupby("name")[["words_ins", "words_del"]].sum().reindex(user_labels, fill_value=0)
    labels = list(reversed(user_labels))
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Inserted",
        y=labels,
        x=totals.loc[labels, "words_ins"].tolist(),
        orientation="h",
        marker_color="#4C72B0",
        hovertemplate="%{y}<br>Inserted: <b>%{x:,}</b><extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Deleted",
        y=labels,
        x=totals.loc[labels, "words_del"].tolist(),
        orientation="h",
        marker_color="#C44E52",
        hovertemplate="%{y}<br>Deleted: <b>%{x:,}</b><extra></extra>",
    ))
    return _apply(fig,
        title="Words Inserted & Deleted by Contributor",
        barmode="group",
        xaxis_tickformat=",",
        xaxis_title="Words",
        yaxis=dict(showgrid=False),
        margin=dict(l=_name_margin(user_labels), r=20, t=54, b=86),
        legend=dict(
            orientation="h",
            x=0.5,
            y=-0.24,
            xanchor="center",
            yanchor="top",
        ),
    )


def chart_share_pie(df, colors, user_labels):
    totals = df.groupby("name")["words_ins"].sum().reindex(user_labels, fill_value=0)
    fig = go.Figure(go.Pie(
        labels=totals.index.tolist(),
        values=totals.values.tolist(),
        marker_colors=[colors.get(n, "#888") for n in totals.index],
        hole=0.45,
        textinfo="percent",
        textposition="inside",
        hovertemplate="<b>%{label}</b><br>%{value:,} words (%{percent})<extra></extra>",
    ))
    return _apply(fig,
        title="Share of Words Written",
        showlegend=True,
        margin=dict(l=20, r=120, t=50, b=20),
        legend=dict(x=1, y=0.5, xanchor="left", yanchor="middle"),
    )


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
        legend=dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
    )


# ── Timeline ──────────────────────────────────────────────────────────────────

def chart_daily_intensity(df, colors, user_labels):
    all_days = pd.date_range(df["day"].min(), df["day"].max(), freq="D")
    pivot = (
        df.groupby(["name", "day"])["words_ins"].sum()
        .unstack(fill_value=0)
        .reindex(index=user_labels, columns=all_days, fill_value=0)
    )
    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="YlGnBu",
        colorbar=dict(title="words"),
        hovertemplate="%{y}<br>%{x|%d %b %Y}<br><b>%{z:,} words</b><extra></extra>",
    ))

    return _apply(fig,
        title="Daily Writing Intensity",
        xaxis_title="Date",
        yaxis=dict(showgrid=False, autorange="reversed"),
        hovermode="x unified",
        margin=dict(l=_name_margin(user_labels), r=20, t=50, b=50),
    )


def chart_session_timeline(sdf, colors, user_labels):
    fig = go.Figure()
    for name in user_labels:
        sub = sdf[sdf["name"] == name]
        color = colors.get(name, "#888")
        fig.add_trace(go.Scatter(
            x=sub["start"].tolist(),
            y=[name] * len(sub),
            mode="markers",
            name=name,
            showlegend=False,
            marker=dict(color=color, size=8, opacity=0.72, line=dict(width=0)),
            hovertemplate="%{x|%d %b %Y, %H:%M}<extra>" + name + "</extra>",
        ))

    return _apply(fig,
        title="Session Timeline",
        xaxis_title="Date",
        yaxis=dict(
            showgrid=True,
            categoryorder="array",
            categoryarray=list(reversed(user_labels)),
        ),
        margin=dict(l=_name_margin(user_labels), r=20, t=50, b=50),
        hovermode="closest",
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
        barmode="stack",
        xaxis_title="Week",
        yaxis_title="Sessions",
        legend=dict(orientation="h", x=0, y=1.08, xanchor="left", yanchor="bottom"),
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
        legend=dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
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
    if top.empty:
        return None

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
        legend=dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
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
    if pct.empty:
        return None
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
    if fp.empty:
        return None
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
        legend=dict(x=0.99, y=0.99, xanchor="right", yanchor="top"),
    )


# ── Aggregator ────────────────────────────────────────────────────────────────

def build_all_charts(data: dict) -> dict:
    df, sdf, user_labels, colors, colors_rgba = _prepare_chart_data(
        data["df"],
        data["sdf"],
        data["user_labels"],
        data["colors"],
        data["colors_rgba"],
    )

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
