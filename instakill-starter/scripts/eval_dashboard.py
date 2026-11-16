"""Static, self-contained HTML dashboard for scripts/evaluate.py (needs the `eval` extra).

One HTML file, charts embedded as base64 PNG, no JavaScript, no server.
Chart rules: a question as title, labelled axes, bars from 0, an interval on every
comparison, one fixed colour per strategy, a diverging colormap centred on 0 for
signed values.
"""
import base64
import html
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

COLORS = {  # the same colour for the same strategy on every chart
    "chronological": "#8c8c8c",
    "popularity": "#e69f00",
    "for_you": "#0072b2",
    "learned": "#009e73",
}


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _errors(intervals):
    return np.array([[iv.mean - iv.low for iv in intervals], [iv.high - iv.mean for iv in intervals]])


def chart_strategies(ev, strategies) -> str:
    ivs = [ev.overall[s] for s in strategies]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(strategies, [iv.mean for iv in ivs], color=[COLORS[s] for s in strategies],
           yerr=_errors(ivs), capsize=6, edgecolor="black", linewidth=0.5)
    ax.set_ylim(bottom=0)
    ax.set_title("Which strategy puts later likes in the top 10?")
    ax.set_xlabel("feed strategy")
    ax.set_ylabel("mean NDCG@10 over users (95 % CI)")
    for i, iv in enumerate(ivs):
        ax.text(i, iv.high, f"{iv.mean:.3f}", ha="center", va="bottom", fontsize=9)
    return _png(fig)


def chart_difference(ev) -> str:
    rows = [("all users", ev.overall["diff"])] + [(n, iv["diff"]) for n, iv in ev.slices.items()]
    rows = [(n, d) for n, d in rows if d.n > 0]
    names = [f"{n} (n={d.n})" for n, d in rows]
    means = np.array([d.mean for _, d in rows])
    limit = max(1e-6, float(np.max(np.abs([v for _, d in rows for v in (d.low, d.high)]))))
    cmap, norm = plt.get_cmap("RdBu"), TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    fig, ax = plt.subplots(figsize=(8, 0.55 * len(rows) + 1.5))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, means, color=cmap(norm(means)), xerr=_errors([d for _, d in rows]),
            capsize=5, edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(y, names)
    ax.set_xlim(-limit * 1.15, limit * 1.15)
    ax.set_title(f"Does learned beat the best baseline ({ev.best_baseline}) in each slice?")
    ax.set_xlabel(f"NDCG@10: learned minus {ev.best_baseline} (95 % paired CI; >0 = learned better)")
    ax.set_ylabel("user slice")
    return _png(fig)


def chart_activity(ev, strategies) -> str:
    groups = [n for n, iv in ev.slices.items() if n in {"new (<10)", "casual (10-49)",
                                                         "regular (50-199)", "power (200+)"}
              and iv["diff"].n > 0]
    width = 0.8 / len(strategies)
    x = np.arange(len(groups))
    fig, ax = plt.subplots(figsize=(8, 4))
    for j, s in enumerate(strategies):
        ivs = [ev.slices[g][s] for g in groups]
        ax.bar(x + (j - (len(strategies) - 1) / 2) * width, [iv.mean for iv in ivs], width,
               yerr=_errors(ivs), capsize=3, color=COLORS[s], label=s, edgecolor="black", linewidth=0.4)
    ax.set_xticks(x, [f"{g}\nn={ev.slices[g]['diff'].n}" for g in groups])
    ax.set_ylim(bottom=0)
    ax.set_title("Which users does each strategy serve, by activity before T?")
    ax.set_xlabel("user activity group (likes before the cut-off)")
    ax.set_ylabel("mean NDCG@10 (95 % CI)")
    ax.legend(title="strategy")
    return _png(fig)


def _md_table_to_html(md: str) -> str:
    out, in_table = [], False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [html.escape(c.strip()).replace("`", "") for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        else:
            if in_table:
                out.append("</table>")
                in_table = False
            if line.startswith("## "):
                out.append(f"<h2>{html.escape(line[3:]).replace('`', '')}</h2>")
            elif line.startswith("# "):
                continue
            elif line.strip():
                out.append(f"<p>{html.escape(line).replace('`', '')}</p>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def dashboard_html(ev) -> str:
    from scripts.evaluate import STRATEGIES, baseline_table_md

    charts = [
        ("Strategies with 95 % intervals", chart_strategies(ev, list(STRATEGIES))),
        ("learned minus the best baseline, per slice", chart_difference(ev)),
        ("Strategies per activity group", chart_activity(ev, list(STRATEGIES))),
    ]
    figures = "\n".join(
        f'<figure><img alt="{html.escape(t)}" src="data:image/png;base64,{b64}"><figcaption>{html.escape(t)}'
        f"</figcaption></figure>" for t, b64 in charts)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>InstaKill feed evaluation</title>
<style>
 body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 16px; color: #1a1a1a; background: #fff; }}
 h1 {{ margin-bottom: .2rem; }} table {{ border-collapse: collapse; margin: .6rem 0 1.4rem; font-size: .9rem; }}
 th, td {{ border: 1px solid #ccc; padding: .3rem .55rem; text-align: left; }} th {{ background: #f2f2f2; }}
 figure {{ margin: 1.5rem 0; }} img {{ max-width: 100%; height: auto; }} figcaption {{ color: #555; font-size: .85rem; }}
 .note {{ color: #555; }}
</style></head><body>
<h1>InstaKill feed evaluation</h1>
<p class="note">Offline time-split replay; generated by scripts/evaluate.py. Protocol: docs/evaluation-protocol.md.
Not comparable with the lab's 1-in-100 exam: here a strategy ranks the whole candidate set and every later like counts.</p>
{figures}
{_md_table_to_html(baseline_table_md(ev))}
</body></html>
"""
