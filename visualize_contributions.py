"""
Overleaf contribution visualizations.
Requires: config.json + usage.json + diff_cache.json (produced by fetch_diffs.py)
"""
import json, re
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import seaborn as sns
import warnings
warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_FILE = Path("config.json")
if not CONFIG_FILE.exists():
    raise SystemExit(
        f"'{CONFIG_FILE}' not found. "
        "Copy config.example.json → config.json and fill in your values."
    )

cfg   = json.loads(CONFIG_FILE.read_text())
TITLE = cfg.get("title", "Overleaf Project")

# Colors/labels resolved after loading data when not set in config (see below).
_cfg_users = cfg.get("users", [])

_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52",
    "#8172B2", "#937860", "#DA8BC3", "#8C8C8C",
]

def short_name(path: str) -> str:
    return (path.replace("LaTeX/chapters/", "")
                .replace("LaTeX/", "")
                .replace(".tex", "")
                .replace(".bib", " (bib)"))

def is_chapter(path: str) -> bool:
    return "chapters/" in path and path.endswith(".tex")

def count_words(text: str) -> int:
    t = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", text)
    t = re.sub(r"\\[a-zA-Z]+", " ", t)
    t = re.sub(r"[{}]", " ", t)
    return len(t.split())

# ── Load data ─────────────────────────────────────────────────────────────────

with open("usage.json") as f:
    updates = json.load(f)["updates"]

with open("diff_cache.json") as f:
    cache = json.load(f)

# ── Resolve authors ───────────────────────────────────────────────────────────
# Use config if provided; otherwise detect from the data and assign palette colors.

if _cfg_users:
    COLORS      = {u["name"]: u["color"] for u in _cfg_users}
    USER_LABELS = [u["name"] for u in _cfg_users]
else:
    seen: dict[str, str] = {}   # id → full name (preserve first-seen order)
    for u in updates:
        for usr in u["meta"]["users"]:
            uid  = usr["id"]
            name = f"{usr['first_name']} {usr['last_name']}"
            seen.setdefault(uid, name)
    USER_LABELS = list(seen.values())
    COLORS      = {name: _PALETTE[i % len(_PALETTE)]
                   for i, name in enumerate(USER_LABELS)}
    print(f"Auto-detected {len(USER_LABELS)} author(s): {', '.join(USER_LABELS)}")

# ── Parse diffs ───────────────────────────────────────────────────────────────

rows = []
for u in updates:
    start = datetime.fromtimestamp(u["meta"]["start_ts"] / 1000)
    end   = datetime.fromtimestamp(u["meta"]["end_ts"]   / 1000)
    session_users = {usr["id"]: f"{usr['first_name']} {usr['last_name']}"
                     for usr in u["meta"]["users"]}

    for path in u["pathnames"]:
        key = f"{u['fromV']}:{u['toV']}:{path}"
        diff_data = cache.get(key, {}).get("diff", [])

        words_ins = defaultdict(int)
        words_del = defaultdict(int)
        chars_ins = defaultdict(int)

        for chunk in diff_data:
            if "i" in chunk:
                chunk_users = {usr["id"]: f"{usr['first_name']} {usr['last_name']}"
                               for usr in chunk["meta"]["users"]}
                w = count_words(chunk["i"])
                c = len(chunk["i"])
                for uid, uname in chunk_users.items():
                    words_ins[uname] += w
                    chars_ins[uname] += c
            elif "d" in chunk:
                chunk_users = {usr["id"]: f"{usr['first_name']} {usr['last_name']}"
                               for usr in chunk["meta"]["users"]}
                w = count_words(chunk["d"])
                for uid, uname in chunk_users.items():
                    words_del[uname] += w

        all_contributors = set(words_ins) | set(words_del) | set(session_users.values())
        for name in all_contributors:
            rows.append({
                "name":      name,
                "path":      path,
                "file":      short_name(path),
                "chapter":   is_chapter(path),
                "start":     start,
                "end":       end,
                "versions":  u["toV"] - u["fromV"],
                "words_ins": words_ins.get(name, 0),
                "words_del": words_del.get(name, 0),
                "chars_ins": chars_ins.get(name, 0),
            })

df = pd.DataFrame(rows)
df["date"]    = df["start"].dt.date
df["weekday"] = df["start"].dt.day_name()
df["hour"]    = df["start"].dt.hour
df["week"]    = df["start"].dt.to_period("W").apply(lambda p: p.start_time)
df["day"]     = df["start"].dt.floor("D")
df["net"]     = df["words_ins"] - df["words_del"]

# Session-level df (one row per session per user, no file split)
srows = []
for u in updates:
    start = datetime.fromtimestamp(u["meta"]["start_ts"] / 1000)
    end   = datetime.fromtimestamp(u["meta"]["end_ts"]   / 1000)
    for usr in u["meta"]["users"]:
        name = f"{usr['first_name']} {usr['last_name']}"
        srows.append({
            "name": name, "start": start, "end": end,
            "versions": u["toV"] - u["fromV"],
            "duration_min": (end - start).total_seconds() / 60,
        })
sdf = pd.DataFrame(srows)
sdf["day"]     = sdf["start"].dt.floor("D")
sdf["week"]    = sdf["start"].dt.to_period("W").apply(lambda p: p.start_time)
sdf["weekday"] = sdf["start"].dt.day_name()
sdf["hour"]    = sdf["start"].dt.hour

DAY_ORDER = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 1 – Overview dashboard
# ─────────────────────────────────────────────────────────────────────────────

fig1 = plt.figure(figsize=(18, 14))
fig1.suptitle(f"{TITLE} – Overleaf Contribution Overview", fontsize=16, fontweight="bold", y=0.99)
gs = GridSpec(3, 3, figure=fig1, hspace=0.50, wspace=0.40)

# 1a – Total words inserted
ax = fig1.add_subplot(gs[0, 0])
totals = df.groupby("name")["words_ins"].sum()
bars = ax.bar(totals.index, totals.values, color=[COLORS[n] for n in totals.index], width=0.5, edgecolor="white")
ax.set_title("Total Words Inserted", fontweight="bold")
ax.set_ylabel("Words")
ax.tick_params(axis="x", rotation=15)
for b, v in zip(bars, totals.values):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 100, f"{v:,}",
            ha="center", va="bottom", fontsize=9, fontweight="bold")
ax.set_ylim(0, totals.max() * 1.2)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

# 1b – Total words deleted
ax = fig1.add_subplot(gs[0, 1])
dels = df.groupby("name")["words_del"].sum()
bars = ax.bar(dels.index, dels.values, color=[COLORS[n] for n in dels.index], width=0.5, edgecolor="white")
ax.set_title("Total Words Deleted", fontweight="bold")
ax.set_ylabel("Words")
ax.tick_params(axis="x", rotation=15)
for b, v in zip(bars, dels.values):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 30, f"{v:,}",
            ha="center", va="bottom", fontsize=9, fontweight="bold")
ax.set_ylim(0, dels.max() * 1.2)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

# 1c – Share of words written (pie)
ax = fig1.add_subplot(gs[0, 2])
net = df.groupby("name")["words_ins"].sum()
ax.pie(net.values, labels=net.index, autopct="%1.1f%%",
       colors=[COLORS[n] for n in net.index], startangle=90,
       wedgeprops={"edgecolor": "white", "linewidth": 1.5})
ax.set_title("Share of Words Written", fontweight="bold")

# 1d – Cumulative words inserted over time
ax = fig1.add_subplot(gs[1, :])
for name in USER_LABELS:
    sub = df[df["name"] == name].sort_values("start")
    cum = sub.groupby("start")["words_ins"].sum().cumsum()
    ax.plot(cum.index, cum.values, marker="o", markersize=3,
            label=name, color=COLORS[name], linewidth=2)
ax.set_title("Cumulative Words Inserted Over Time", fontweight="bold")
ax.set_ylabel("Cumulative words")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=40, ha="right")
ax.legend()
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.grid(axis="y", alpha=0.3)

# 1e – Weekly word output stacked bar
ax = fig1.add_subplot(gs[2, :2])
weekly_w = df.groupby(["week", "name"])["words_ins"].sum().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in weekly_w.columns: weekly_w[name] = 0
x = np.arange(len(weekly_w))
bottom = np.zeros(len(weekly_w))
for name in USER_LABELS:
    ax.bar(x, weekly_w[name].values, bottom=bottom, label=name,
           color=COLORS[name], edgecolor="white", alpha=0.9)
    bottom += weekly_w[name].values
ax.set_xticks(x)
ax.set_xticklabels([str(d.date()) for d in weekly_w.index], rotation=45, ha="right", fontsize=8)
ax.set_title("Words Inserted per Week", fontweight="bold")
ax.set_ylabel("Words")
ax.legend()
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

# 1f – Total sessions bar
ax = fig1.add_subplot(gs[2, 2])
sc = sdf.groupby("name").size()
bars = ax.bar(sc.index, sc.values, color=[COLORS[n] for n in sc.index], width=0.5, edgecolor="white")
ax.set_title("Total Edit Sessions", fontweight="bold")
ax.set_ylabel("Sessions")
ax.tick_params(axis="x", rotation=15)
for b, v in zip(bars, sc.values):
    ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.3, str(v),
            ha="center", va="bottom", fontweight="bold")
ax.set_ylim(0, sc.max() * 1.18)

fig1.savefig("contributions_overview.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_overview.png")
plt.close(fig1)

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 2 – Temporal patterns
# ─────────────────────────────────────────────────────────────────────────────

fig2, axes = plt.subplots(2, 2, figsize=(16, 11))
fig2.suptitle(f"{TITLE} – Temporal Contribution Patterns", fontsize=15, fontweight="bold")

ax = axes[0, 0]
pivot = sdf.groupby(["weekday","hour"]).size().unstack(fill_value=0)
pivot = pivot.reindex([d for d in DAY_ORDER if d in pivot.index])
sns.heatmap(pivot, ax=ax, cmap="YlOrRd", linewidths=0.4, linecolor="#ccc",
            annot=True, fmt="d", cbar_kws={"label": "sessions"})
ax.set_title("Sessions by Hour & Weekday", fontweight="bold")
ax.set_xlabel("Hour of day"); ax.set_ylabel("")

ax = axes[0, 1]
for name in USER_LABELS:
    h = sdf[sdf["name"]==name].groupby("hour").size().reindex(range(24), fill_value=0)
    ax.plot(range(24), h.values, marker="o", markersize=4,
            label=name, color=COLORS[name], linewidth=2)
ax.set_title("Activity by Hour of Day", fontweight="bold")
ax.set_xlabel("Hour"); ax.set_ylabel("Sessions")
ax.set_xticks(range(0,24,2)); ax.legend(); ax.grid(axis="y", alpha=0.4)

ax = axes[1, 0]
weekly_s = sdf.groupby(["week","name"]).size().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in weekly_s.columns: weekly_s[name] = 0
x = np.arange(len(weekly_s)); w = 0.35
for i, name in enumerate(USER_LABELS):
    ax.bar(x + (i-0.5)*w, weekly_s[name].values, width=w,
           label=name, color=COLORS[name], alpha=0.9, edgecolor="white")
ax.set_xticks(x)
ax.set_xticklabels([str(d.date()) for d in weekly_s.index], rotation=45, ha="right", fontsize=8)
ax.set_title("Sessions per Week", fontweight="bold"); ax.set_ylabel("Sessions")
ax.legend(); ax.grid(axis="y", alpha=0.4)

ax = axes[1, 1]
dow = sdf.groupby(["weekday","name"]).size().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in dow.columns: dow[name] = 0
dow = dow.reindex([d for d in DAY_ORDER if d in dow.index])
x = np.arange(len(dow))
for i, name in enumerate(USER_LABELS):
    ax.bar(x + (i-0.5)*0.35, dow[name].values, width=0.35,
           label=name, color=COLORS[name], alpha=0.9, edgecolor="white")
ax.set_xticks(x); ax.set_xticklabels(dow.index, rotation=20, ha="right")
ax.set_title("Sessions by Day of Week", fontweight="bold"); ax.set_ylabel("Sessions")
ax.legend(); ax.grid(axis="y", alpha=0.4)

fig2.tight_layout()
fig2.savefig("contributions_temporal.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_temporal.png")
plt.close(fig2)

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 3 – Chapter breakdown
# ─────────────────────────────────────────────────────────────────────────────

chap = df[df["chapter"]].copy()

fig3, axes = plt.subplots(1, 2, figsize=(18, 9))
fig3.suptitle(f"{TITLE} – Chapter-Level Contributions (words inserted)", fontsize=15, fontweight="bold")

# 3a – Top chapters stacked horizontal bar
ax = axes[0]
fp = chap.groupby(["file","name"])["words_ins"].sum().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in fp.columns: fp[name] = 0
fp["total"] = fp[USER_LABELS].sum(axis=1)
top = fp.nlargest(20, "total").drop(columns="total")
y = np.arange(len(top)); left = np.zeros(len(top))
for name in USER_LABELS:
    ax.barh(y, top[name].values, left=left, label=name,
            color=COLORS[name], alpha=0.9, edgecolor="white")
    left += top[name].values
ax.set_yticks(y); ax.set_yticklabels(top.index, fontsize=9); ax.invert_yaxis()
ax.set_title("Top 20 Chapters by Words Inserted", fontweight="bold")
ax.set_xlabel("Words inserted"); ax.legend(); ax.grid(axis="x", alpha=0.4)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

# 3b – Per-chapter word split scatter
ax = axes[1]
fp2 = chap.groupby(["file","name"])["words_ins"].sum().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in fp2.columns: fp2[name] = 0
fp2 = fp2[(fp2[USER_LABELS] > 0).any(axis=1)]
u1, u2 = USER_LABELS[0], USER_LABELS[1]
total_w = fp2[u1] + fp2[u2]
sizes_scaled = 20 + 300 * total_w / total_w.max()
ax.scatter(fp2[u1], fp2[u2], s=sizes_scaled,
           color="#7B9CC9", alpha=0.7, edgecolors="#3a5f8a", linewidth=0.8)
top10_idx = total_w.nlargest(10).index
for fname in top10_idx:
    row = fp2.loc[fname]
    ax.annotate(fname, (row[u1], row[u2]), fontsize=7.5,
                xytext=(4, 4), textcoords="offset points", color="#333")
maxv = max(fp2[u1].max(), fp2[u2].max()) * 1.1
ax.plot([0, maxv], [0, maxv], "--", color="gray", alpha=0.4, linewidth=1, label="equal split")
ax.set_xlabel(f"Words by {u1}", fontsize=10)
ax.set_ylabel(f"Words by {u2}", fontsize=10)
ax.set_title("Per-Chapter Word Split\n(bubble size = total words)", fontweight="bold")
ax.legend(); ax.grid(alpha=0.3)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

fig3.tight_layout()
fig3.savefig("contributions_files.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_files.png")
plt.close(fig3)

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 4 – Timeline dot strip
# ─────────────────────────────────────────────────────────────────────────────

fig4, axes4 = plt.subplots(2, 1, figsize=(18, 7), sharex=True)
fig4.suptitle(f"{TITLE} – Contribution Timeline (each dot = one session)", fontsize=14, fontweight="bold")

rng = np.random.default_rng(42)
for ax4, name in zip(axes4, USER_LABELS):
    sub = sdf[sdf["name"] == name].copy()
    jitter = rng.uniform(-0.25, 0.25, size=len(sub))
    ax4.scatter(sub["start"], jitter, c=COLORS[name], alpha=0.7, s=50, linewidths=0, zorder=3)
    ax4.axhline(0, color="#ccc", linewidth=0.5, zorder=1)
    ax4.set_ylabel(name, fontsize=11, fontweight="bold")
    ax4.set_yticks([]); ax4.set_ylim(-1, 1)
    ax4.grid(axis="x", alpha=0.3, zorder=0)
    ax4.text(0.01, 0.85, f"{len(sub)} sessions", transform=ax4.transAxes,
             fontsize=10, color=COLORS[name], fontweight="bold")

axes4[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
axes4[-1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
plt.setp(axes4[-1].xaxis.get_majorticklabels(), rotation=40, ha="right")
axes4[-1].set_xlabel("Date")
fig4.tight_layout()
fig4.savefig("contributions_timeline.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_timeline.png")
plt.close(fig4)

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 5 – Daily writing intensity
# ─────────────────────────────────────────────────────────────────────────────

fig5, axes5 = plt.subplots(2, 1, figsize=(18, 8), sharex=True)
fig5.suptitle(f"{TITLE} – Daily Writing Intensity (words inserted per day)", fontsize=14, fontweight="bold")

all_days = pd.date_range(df["day"].min(), df["day"].max(), freq="D")
for ax5, name in zip(axes5, USER_LABELS):
    sub = df[df["name"] == name].groupby("day")["words_ins"].sum().reindex(all_days, fill_value=0)
    ax5.bar(sub.index, sub.values, color=COLORS[name], alpha=0.85, width=0.9, edgecolor="none")
    ax5.set_ylabel("Words", fontsize=10)
    ax5.set_title(name, fontweight="bold", color=COLORS[name])
    ax5.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax5.grid(axis="y", alpha=0.3)
    peak_day = sub.idxmax()
    peak_val = sub.max()
    if peak_val > 0:
        ax5.annotate(f"peak: {peak_val:,}\n{peak_day.strftime('%d %b')}",
                     xy=(peak_day, peak_val), xytext=(15, -10),
                     textcoords="offset points", fontsize=8, color=COLORS[name],
                     arrowprops=dict(arrowstyle="->", color=COLORS[name], lw=1))

axes5[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
axes5[-1].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
plt.setp(axes5[-1].xaxis.get_majorticklabels(), rotation=40, ha="right")
fig5.tight_layout()
fig5.savefig("contributions_intensity.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_intensity.png")
plt.close(fig5)

# ─────────────────────────────────────────────────────────────────────────────
#  FIGURE 6 – Editing patterns + chapter ownership heatmap
# ─────────────────────────────────────────────────────────────────────────────

fig6, axes6 = plt.subplots(1, 2, figsize=(18, 9))
fig6.suptitle(f"{TITLE} – Editing Patterns", fontsize=15, fontweight="bold")

# 6a – Insertions vs deletions scatter
ax = axes6[0]
for name in USER_LABELS:
    sub = df[(df["name"]==name) & (df["chapter"]) & ((df["words_ins"]>0) | (df["words_del"]>0))]
    ax.scatter(sub["words_ins"], sub["words_del"], label=name,
               color=COLORS[name], alpha=0.6, s=40, edgecolors="white", linewidth=0.5)
max_v = max(df["words_ins"].max(), df["words_del"].max()) * 1.05
ax.plot([0, max_v], [0, max_v], "--", color="gray", alpha=0.5, linewidth=1, label="ins = del")
ax.set_xlabel("Words inserted"); ax.set_ylabel("Words deleted")
ax.set_title("Insertions vs. Deletions per File Edit\n(chapter files only)", fontweight="bold")
ax.legend(); ax.grid(alpha=0.3)
ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

# 6b – Chapter ownership heatmap
ax = axes6[1]
pct = chap.groupby(["file","name"])["words_ins"].sum().unstack(fill_value=0)
for name in USER_LABELS:
    if name not in pct.columns: pct[name] = 0
pct["total"] = pct[USER_LABELS].sum(axis=1)
pct = pct[pct["total"] > 50]
for name in USER_LABELS:
    pct[name] = pct[name] / pct["total"] * 100
pct = pct[USER_LABELS].sort_values(USER_LABELS[0], ascending=True)
sns.heatmap(pct, ax=ax, cmap="RdYlBu_r", vmin=0, vmax=100,
            annot=True, fmt=".0f", linewidths=0.5, linecolor="#eee",
            cbar_kws={"label": "% of words inserted"})
ax.set_title("Chapter Ownership (% words per author)", fontweight="bold")
ax.set_xlabel(""); ax.set_ylabel("")
ax.set_xticklabels(ax.get_xticklabels(), rotation=20, ha="right")

fig6.tight_layout()
fig6.savefig("contributions_patterns.png", dpi=150, bbox_inches="tight")
print("Saved: contributions_patterns.png")
plt.close(fig6)

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n── Summary ──────────────────────────────────────────────────────")
for name in USER_LABELS:
    sub  = df[df["name"] == name]
    ssub = sdf[sdf["name"] == name]
    print(f"\n{name}")
    print(f"  Sessions       : {len(ssub)}")
    print(f"  Words inserted : {sub['words_ins'].sum():,}")
    print(f"  Words deleted  : {sub['words_del'].sum():,}")
    print(f"  Net words      : {sub['net'].sum():,}")
    print(f"  Files touched  : {sub['file'].nunique()}")

print("\nAll plots generated.")
