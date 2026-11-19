"""Standalone paired plots. Every resource point is drawn, including the tails."""

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
import numpy as np

from measure import MODELS, OUT, SMELLS


NAMES = {"FE": "Feature Envy", "GC": "God Class", "LM": "Long Method"}
MODEL_NAMES = {"gpt": "GPT", "glm": "GLM", "deepseek": "DeepSeek"}
COLORS = {"FE": "#1d706f", "GC": "#916029", "LM": "#58568b"}
INK, MUTED, RULE = "#172e39", "#4b606a", "#d6dfe1"


def configure():
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for font in (
        "Hiragino Sans GB",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Microsoft YaHei",
        "WenQuanYi Zen Hei",
        "SimHei",
    ):
        if font in installed:
            break
    else:
        raise RuntimeError("Rendering the Chinese labels requires a Chinese system font.")
    plt.rcParams.update(
        {
            "font.family": ["DejaVu Sans", font],
            "font.size": 10,
            "text.color": INK,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.edgecolor": RULE,
            "axes.unicode_minus": True,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def ratio_label(value, _=None):
    if value >= 1:
        return f"{value:g}×"
    return f"1/{round(1 / value):g}×"


def ratio_axis(ax, low, high, axis="y", max_ticks=8):
    a, b = math.floor(math.log2(low)), math.ceil(math.log2(high))
    gap = max(1, math.ceil((b - a) / max_ticks))
    ticks = [2.0**i for i in range(a, b + 1) if i % gap == 0]
    axis_obj = ax.yaxis if axis == "y" else ax.xaxis
    getattr(ax, "set_" + axis + "scale")("log", base=2)
    getattr(ax, "set_" + axis + "lim")(low, high)
    axis_obj.set_major_locator(FixedLocator(ticks))
    axis_obj.set_minor_locator(NullLocator())
    axis_obj.set_major_formatter(FuncFormatter(ratio_label))


def head(fig, title, subtitle):
    fig.text(0.072, 0.966, title, fontsize=21, weight="bold", va="top")
    fig.text(0.072, 0.911, subtitle, fontsize=10.5, color=MUTED, va="top")


def write(fig, name):
    fig.savefig(OUT / name, dpi=170, facecolor="white")
    plt.close(fig)


def success_plot(rows):
    fig = plt.figure(figsize=(11.5, 5.7))
    head(
        fig,
        "GPT 修复成功率的配对变化",
        "每个点汇总同一组双边均已判定的原题。点为通过率差，横线为按仓库重抽样的 95% 区间。",
    )
    ax = fig.add_axes([0.205, 0.17, 0.51, 0.60])
    table = fig.add_axes([0.738, 0.17, 0.24, 0.60], sharey=ax)
    table.axis("off")
    seq = [
        next(row for row in rows if row["smell"] == smell and row["level"] == level)
        for smell in SMELLS
        for level in ("S0", "S2")
    ]
    loc = [6.3, 5.3, 3.9, 2.9, 1.5, 0.5]
    ax.set_ylim(-0.1, 7.0)
    ax.axvline(0, ls="--", color=MUTED, lw=1)
    for y, row in zip(loc, seq):
        c = COLORS[row["smell"]]
        ax.hlines(y, row["lo"], row["hi"], color=c, lw=2.3)
        ax.scatter(row["pp"], y, s=45, marker="D" if row["level"] == "S2" else "o", color=c, zorder=3)
        ax.text(row["pp"], y + 0.21, f"{row['pp']:+.1f}", ha="center", va="bottom", fontsize=9, color=c)
        for xx, k in zip([0.10, 0.48, 0.84], ["n", "gain", "loss"]):
            table.text(
                xx, y, str(row[k]), transform=table.get_yaxis_transform(), ha="center", va="center"
            )
    for xx, name in zip([0.10, 0.48, 0.84], ["配对数", "转通过", "转失败"]):
        table.text(xx, 1.045, name, transform=table.transAxes, ha="center", color=MUTED, fontsize=9.5)
    ax.set_yticks(loc, [NAMES[r["smell"]] + "  " + r["level"] for r in seq])
    ax.tick_params(axis="y", length=0, pad=9)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", lw=0.5, color=RULE)
    ax.set_xlabel("通过率差（注入减对照，百分点）", labelpad=9)
    write(fig, "success-estimates.png")


def behavior_plot(frame):
    fig, axes = plt.subplots(1, 3, figsize=(13.3, 5.5))
    head(
        fig,
        "同一道任务多走几轮，token 会怎样变化？",
        "横轴是模型轮数比，纵轴是总 token 比。对角线上的任务每轮平均 token 相同，线的上方表示每轮平均 token 也增加了。",
    )
    fig.subplots_adjust(left=0.087, right=0.97, top=0.77, bottom=0.18, wspace=0.16)
    x, y = np.exp(frame.log_steps), np.exp(frame.log_tokens)
    low, high = min(x.min(), y.min()) / 1.12, max(x.max(), y.max()) * 1.1
    for ax, model in zip(axes, MODELS):
        g = frame[frame.model == model]
        for s in SMELLS:
            z = g[g.smell == s]
            ax.scatter(
                np.exp(z.log_steps), np.exp(z.log_tokens), s=8, color=COLORS[s], alpha=0.22, lw=0
            )
        ax.plot([low, high], [low, high], color=INK, lw=1)
        ax.axhline(1, color=MUTED, lw=0.6, ls="--")
        ax.axvline(1, color=MUTED, lw=0.6, ls="--")
        ratio_axis(ax, low, high, "x", 5)
        ratio_axis(ax, low, high, "y", 5)
        ax.set_title(MODEL_NAMES[model], weight="bold", fontsize=13)
        ax.set_xlabel("模型轮数比", labelpad=6)
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("总 token 比")
    fig.text(
        0.09,
        0.045,
        "绿色为 Feature Envy，棕色为 God Class，紫色为 Long Method。三个强度均纳入。",
        fontsize=9,
        color=MUTED,
    )
    write(fig, "behavior-scatter.png")


def render(frame, success):
    configure()
    success_plot(success)
    behavior_plot(frame)
