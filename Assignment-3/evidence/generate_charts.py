#!/usr/bin/env python3
"""
Generates the chart PNGs embedded in docs/cost-report.md and README.md, from
cost_model_output.json (run cost_model.py first if that file is stale).

Palette follows the repo's dataviz skill's validated default (references/palette.md):
light chart surface, fixed categorical hue order, status green/red reserved for
savings/cost polarity rather than generic series identity.

Run: python3 generate_charts.py   (writes PNGs into charts/)
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(HERE, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

with open(os.path.join(HERE, "cost_model_output.json")) as f:
    DATA = json.load(f)

# --- Palette (references/palette.md, light mode) -----------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE_LINE = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1 - "normal month" / Singapore
ORANGE = "#eb6834"    # categorical slot 2 - "exam month"
AQUA = "#1baf7a"       # categorical slot 3 - Mumbai
GOOD_GREEN = "#0ca30c"  # status: savings / optimized
CRITICAL_RED = "#d03b3b"  # status: baseline / over-budget

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "text.color": INK,
    "axes.edgecolor": BASELINE_LINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.size": 11,
})


def clean_axes(ax, hide_y=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(not hide_y)
    if hide_y:
        ax.set_yticks([])
    ax.tick_params(length=0)


# ---------------------------------------------------------------------------
# Chart 1: baseline per-service cost, normal vs exam month (Singapore)
# -> shows the "three most expensive components" finding directly.
# ---------------------------------------------------------------------------
def chart_service_breakdown():
    region = "ap-southeast-1"
    normal = DATA["baseline"][region]["normal"]
    exam = DATA["baseline"][region]["exam"]
    services = sorted(set(normal) | set(exam), key=lambda s: exam.get(s, 0), reverse=True)
    services = [s for s in services if exam.get(s, 0) + normal.get(s, 0) > 0.01][:12]
    labels = [s.replace(" [hidden]", "").replace(" [hidden - backups/rotation]", "") for s in services]

    fig, ax = plt.subplots(figsize=(10, 6.5))
    y = range(len(services))
    h = 0.36
    n_vals = [normal.get(s, 0) for s in services]
    e_vals = [exam.get(s, 0) for s in services]

    ax.barh([i + h / 2 + 0.04 for i in y], n_vals, height=h, color=BLUE, label="Normal month")
    ax.barh([i - h / 2 - 0.04 for i in y], e_vals, height=h, color=ORANGE, label="Exam month")

    for i, v in enumerate(n_vals):
        ax.text(v + max(e_vals) * 0.015, i + h / 2 + 0.04, f"${v:,.0f}", va="center", fontsize=9, color=INK_SECONDARY)
    for i, v in enumerate(e_vals):
        ax.text(v + max(e_vals) * 0.015, i - h / 2 - 0.04, f"${v:,.0f}", va="center", fontsize=9, color=INK_SECONDARY)

    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("USD / month")
    ax.set_title("Singapore (ap-southeast-1) — baseline monthly cost per service", fontsize=13, loc="left", pad=14)
    ax.xaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    clean_axes(ax, hide_y=False)
    ax.spines["left"].set_color(GRIDLINE)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "service-breakdown-singapore.png"), dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 2: baseline vs optimized avg monthly cost, both regions, vs budget
# ---------------------------------------------------------------------------
def chart_baseline_vs_optimized():
    regions = [("ap-southeast-1", "Singapore"), ("ap-south-1", "Mumbai")]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    x = range(len(regions))
    w = 0.32

    baseline_avg, optimized_avg = [], []
    for code, _ in regions:
        n, e = DATA["baseline"][code]["normal"], DATA["baseline"][code]["exam"]
        tn, te = sum(n.values()), sum(e.values())
        baseline_avg.append((tn * 10 + te * 2) / 12)
        on, oe = DATA["optimized"][code]["normal"], DATA["optimized"][code]["exam"]
        ton, toe = sum(on.values()), sum(oe.values())
        optimized_avg.append((ton * 10 + toe * 2) / 12)

    b1 = ax.bar([i - w / 2 - 0.02 for i in x], baseline_avg, width=w, color=CRITICAL_RED, label="Baseline (A2 design, redeployed)")
    b2 = ax.bar([i + w / 2 + 0.02 for i in x], optimized_avg, width=w, color=GOOD_GREEN, label="Optimized (this assignment)")

    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            ax.text(rect.get_x() + rect.get_width() / 2, h + 10, f"${h:,.0f}", ha="center", fontsize=10, color=INK)

    ax.axhline(1000, color=INK_MUTED, linewidth=1.4, linestyle=(0, (5, 3)))
    ax.text(len(regions) - 0.5 + 0.02, 1000, "  $1,000/mo budget", va="center", fontsize=9.5, color=INK_MUTED)

    ax.set_xticks(list(x))
    ax.set_xticklabels([name for _, name in regions], fontsize=11)
    ax.set_ylabel("USD / month (averaged over the year)")
    ax.set_title("Average monthly cost vs. the $1,000 budget", fontsize=13, loc="left", pad=14)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    clean_axes(ax, hide_y=False)
    ax.spines["left"].set_color(GRIDLINE)
    ax.set_ylim(0, 1150)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "baseline-vs-optimized.png"), dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 3: per-optimization annual savings (Singapore)
# ---------------------------------------------------------------------------
def chart_optimization_savings():
    region = "ap-southeast-1"
    sa = DATA["savings_annual"][region]
    labels = ["A: NAT consolidation\n+ VPC endpoints", "B: Autosave to\nDynamoDB on-demand", "C: CloudFront\ncompression + TTLs"]
    keys = ["A: NAT consolidation + VPC endpoints", "B: autosave -> DynamoDB on-demand", "C: CloudFront compression + cache TTLs"]
    savings = [sa[k] for k in keys]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, savings, width=0.5, color=GOOD_GREEN)
    for rect, v in zip(bars, savings):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 10, f"${v:,.0f}/yr", ha="center", fontsize=11, color=INK)

    total = sum(savings)
    ax.set_title(f"Annual savings per optimization — Singapore (total ${total:,.0f}/yr, 26% off baseline)",
                 fontsize=12.5, loc="left", pad=14)
    ax.set_ylabel("USD / year saved")
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    clean_axes(ax, hide_y=False)
    ax.spines["left"].set_color(GRIDLINE)
    ax.set_ylim(0, max(savings) * 1.25)
    fig.tight_layout()
    fig.savefig(os.path.join(CHARTS_DIR, "optimization-savings.png"), dpi=160)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 4: region comparison - cost and modelled Bhutan latency
# ---------------------------------------------------------------------------
def chart_region_comparison():
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))

    # Cost panel
    ax = axes[0]
    regions = ["Singapore\n(ap-southeast-1)", "Mumbai\n(ap-south-1)"]
    costs = []
    for code in ("ap-southeast-1", "ap-south-1"):
        on, oe = DATA["optimized"][code]["normal"], DATA["optimized"][code]["exam"]
        ton, toe = sum(on.values()), sum(oe.values())
        costs.append((ton * 10 + toe * 2) / 12)
    bars = ax.bar(regions, costs, width=0.45, color=[BLUE, AQUA])
    for rect, v in zip(bars, costs):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 5, f"${v:,.0f}/mo", ha="center", fontsize=10.5, color=INK)
    ax.set_title("Optimized avg cost/month", fontsize=12, loc="left")
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax.set_axisbelow(True)
    clean_axes(ax, hide_y=False)
    ax.spines["left"].set_color(GRIDLINE)
    ax.set_ylim(0, max(costs) * 1.3)

    # Latency panel (modelled, see docs/cost-report.md Section 4 for the formula)
    ax2 = axes[1]
    dist = [3274, 1947]
    rtt = [65.8, 47.3]
    bars2 = ax2.bar(regions, rtt, width=0.45, color=[BLUE, AQUA])
    for rect, v, d in zip(bars2, rtt, dist):
        ax2.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 1.5,
                  f"~{v:.0f} ms\n({d:,} km)", ha="center", fontsize=10, color=INK)
    ax2.set_title("Modelled RTT from Thimphu, Bhutan", fontsize=12, loc="left")
    ax2.yaxis.grid(True, color=GRIDLINE, linewidth=0.8)
    ax2.set_axisbelow(True)
    clean_axes(ax2, hide_y=False)
    ax2.spines["left"].set_color(GRIDLINE)
    ax2.set_ylim(0, max(rtt) * 1.35)

    fig.suptitle("Region comparison: Mumbai is cheaper and lower-latency for Bhutan — see cost-report.md §4 for caveats",
                 fontsize=11.5, color=INK_SECONDARY, x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(os.path.join(CHARTS_DIR, "region-comparison.png"), dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    chart_service_breakdown()
    chart_baseline_vs_optimized()
    chart_optimization_savings()
    chart_region_comparison()
    print(f"Wrote 4 charts to {CHARTS_DIR}")
