"""Publication-grade figures anchored on deep structural-logic dimensions & 4-stage agent trajectories."""

from __future__ import annotations

import json
from matplotlib.transforms import offset_copy

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

from core import DATA, HERE, LEVELS, MODEL_SHORT, MODELS, SMELL_NAME, SMELLS

FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
(FIG / "slide").mkdir(exist_ok=True)
STATE = {"out": FIG, "notitle": False}

R = json.loads((DATA / "results.json").read_text())
DS = R["deep_structure"]

COL = {"gpt": "#1b7f79", "glm": "#d9822b", "deepseek": "#5b4b9a"}
SCOL = {"FE": "#3b75af", "GC": "#c0392b", "LM": "#2e8b57"}
MARK = {"FE": "o", "GC": "s", "LM": "^"}
INK, MUTED, GRID = "#1f2a36", "#6b7785", "#e6e9ee"

plt.rcParams.update({
    "font.family": ["PingFang SC", "Heiti SC", "Arial Unicode MS"],
    "font.size": 10.5, "axes.edgecolor": "#9aa5b1", "axes.linewidth": 0.8, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.titleweight": "bold", "axes.titlesize": 11.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "legend.frameon": False, "savefig.dpi": 220, "savefig.bbox": "tight",
    "axes.unicode_minus": False,
})

LEVEL_LABEL = {
    "FE": ["无坏味", "S0\nATFD 5–7", "S1\nATFD 8–10", "S2\nATFD 11–13"],
    "GC": ["无坏味", "S0\n1k–3k 行", "S1\n3k–5k 行", "S2\n5k–7k 行"],
    "LM": ["无坏味", "S0\n60–120", "S1\n120–240", "S2\n240–480"],
    "ALL": ["无坏味", "S0\n轻度", "S1\n中度", "S2\n重度"],
}


def cell(m, s, lv):
    for c in R["dose_cells"]:
        if c["model"] == m and c["smell"] == s and c["level"] == lv:
            return c
    raise KeyError((m, s, lv))


def title(fig, main, sub=None):
    if STATE["notitle"]:
        return
    y = 0.93 + (38 if sub else 16) / (fig.get_figheight() * 72)
    fig.text(0.01, y, main, ha="left", va="bottom", fontsize=14.6, weight="bold", color=INK)
    if sub:
        tr = offset_copy(fig.transFigure, fig=fig, x=0, y=-6, units="points")
        fig.text(0.01, y, sub, ha="left", va="top", fontsize=10.2, color=MUTED, transform=tr)


def legend_models(ax, loc="upper left", **kw):
    ax.legend(handles=[plt.Line2D([], [], color=COL[m], marker="o", lw=2, label=MODEL_SHORT[m]) for m in MODELS],
              loc=loc, **kw)


# ---------------------------------------------------------------- F1 overview (with S0/S1/S2)
def fig1():
    fig, axes = plt.subplots(1, 4, figsize=(14.6, 4.2), gridspec_kw=dict(width_ratios=[1, 1, 1, 1.18], wspace=0.32))
    alphas = [0.40, 0.68, 0.96]
    width = 0.24
    for ax, key, lab in zip(axes[:3], ["tokens", "steps", "seconds"], ["总 Token 消耗", "交互步数（真实行为时长）", "墙钟耗时"]):
        for i, m in enumerate(MODELS):
            top_hi = 0.0
            for j, lv in enumerate(LEVELS):
                v, lo, hi = cell(m, "ALL", lv)[key]
                xpos = i + (j - 1) * (width + 0.02)
                ax.bar(xpos, max(v, 0), width, color=COL[m], alpha=alphas[j], edgecolor="white", lw=0.6, zorder=2)
                ax.errorbar(xpos, v, yerr=[[v - lo], [hi - v]], fmt="none", ecolor=INK, capsize=2.5, lw=0.95, zorder=3)
                top_hi = max(top_hi, hi)
            mv = R["overall"][m][key][0]
            ax.text(i, top_hi + 2.2, f"均值 +{mv:.0f}%", ha="center", va="bottom", fontsize=9.0, color=COL[m], weight="bold")
        ax.axhline(0, color=MUTED, lw=1, ls="--")
        ax.set_xticks(range(3), [MODEL_SHORT[m] for m in MODELS])
        ax.set_xlim(-0.55, 2.55)
        ax.set_ylim(-6, 63)
        ax.set_title(lab, loc="left")
        ax.set_ylabel("相对干净代码的变化 (%)" if key == "tokens" else "")
    axes[0].legend(
        handles=[Patch(facecolor="#556270", alpha=a, label=l) for a, l in zip(alphas, ["S0 轻度", "S1 中度", "S2 重度"])],
        loc="upper left", fontsize=8.8, handlelength=1.2, labelspacing=0.3,
    )
    axes[2].text(-0.48, 48, "注：受分批时延影响\n（DS 呈 S0→S2 倒挂）", fontsize=7.9, color=MUTED, ha="left", va="top")

    ax = axes[3]
    y_labels = ["S0 轻度", "S1 中度", "S2 重度", "总体合并"]
    plot_rows = [(0, R["success"]["S0"], "o"), (2, R["success"]["S2"], "o"), (3, R["success"]["pooled"], "D")]
    for y, d, mk in plot_rows:
        v, lo, hi = d["pp"]
        ax.errorbar(v, y, xerr=[[v - lo], [hi - v]], fmt=mk, ms=7.5, color=COL["gpt"], capsize=4.5, lw=1.9, zorder=3)
        ax.text(v, y + 0.28, f"{v:+.1f} 个百分点", ha="center", va="top", fontsize=8.8, color=COL["gpt"],
                weight="bold" if y == 3 else "normal")
    ax.text(-1.2, 1.0, "（仓内未提供 S1 评测结果）", ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.axhline(2.5, color="#cbd2d9", lw=0.9, ls=":")
    ax.axvline(0, color=MUTED, lw=1, ls="--")
    ax.axvspan(-5, 5, color="#e8f3f2", zorder=0)
    ax.set_yticks(range(4), y_labels)
    ax.set_xlim(-9, 6)
    ax.set_ylim(-0.55, 3.68)
    ax.invert_yaxis()
    ax.set_xlabel("GPT 通过率变化（百分点）")
    ax.set_title("任务通过率（仅 GPT 有评测）", loc="left")
    ax.text(3.65, 0.55, "±5 个百分点\n波动范围", ha="center", va="center", fontsize=8.0, color=COL["gpt"])
    title(fig, "图 1  全局表现：代码结构退化主要推高理解与交互成本，强模型通过率变化不超过 5 个百分点",
          "同题同模型配对比较；浅→深三柱对应 S0/S1/S2 三个严重度档位，误差线为按仓库聚类的 95% 置信区间")
    fig.savefig(STATE["out"] / "fig1_overview.png")
    plt.close(fig)


# ---------------------------------------------------------------- F2 dose curves
def fig2():
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.3), sharey=True, gridspec_kw=dict(wspace=0.12))
    sub_titles = {"FE": "依恋情结（数据–行为分离）", "GC": "上帝类（异质职责混杂）",
                  "LM": "长方法（控制流内联膨胀）", "ALL": "三类汇总平均"}
    for ax, s in zip(axes, SMELLS + ["ALL"]):
        for m in MODELS:
            ys = [0] + [cell(m, s, lv)["tokens"][0] for lv in LEVELS]
            lo = [0] + [cell(m, s, lv)["tokens"][1] for lv in LEVELS]
            hi = [0] + [cell(m, s, lv)["tokens"][2] for lv in LEVELS]
            x = np.arange(4)
            ax.fill_between(x, lo, hi, color=COL[m], alpha=0.12, lw=0)
            ax.plot(x, ys, "-o", color=COL[m], lw=2.2, ms=6)
        ax.axhline(0, color=MUTED, lw=1, ls="--")
        ax.axvspan(-0.15, 1, color="#fdf1e6", zorder=0)
        ax.set_xticks(range(4), LEVEL_LABEL[s], fontsize=9)
        ax.set_xlim(-0.15, 3.22)
        ax.set_title(sub_titles[s], loc="left", fontsize=11.2)
        ax.set_xlabel({"FE": "跨类访问属性数 ATFD", "GC": "类有效代码行数", "LM": "方法有效代码行数", "ALL": "严重度档位"}[s],
                      fontsize=9, color=MUTED)
        if s == "ALL":
            for m in MODELS:
                sh = R["escalation"][m]["ALL"]["onset_share"]
                ax.text(3.08, cell(m, "ALL", "S2")["tokens"][0], f"{sh:.0%}", color=COL[m], fontsize=9.5, va="center",
                        weight="bold")
            ax.text(1.05, 62, "右侧数字 = S0 已占 S2 总增幅的比例", fontsize=8.3, color=MUTED)
    axes[0].set_ylabel("总 Token 增幅 (%)")
    axes[0].set_ylim(-8, 68)
    axes[0].text(0.5, 60, "破界跃升区", ha="center", color="#b5651d", fontsize=9.5)
    legend_models(axes[0], loc="upper right", fontsize=9)
    title(fig, "图 2  影响曲线：轻度退化（S0）已产生七至九成开销，仅控制流膨胀型坏味随严重度持续爬升",
          "从干净代码到 S0 即贡献了 S2 总增幅的 68%（GPT）、78%（GLM）、88%（DeepSeek）；S0 到 S2 仅长方法显著上升")
    fig.savefig(STATE["out"] / "fig2_dose_curves.png")
    plt.close(fig)


# ---------------------------------------------------------------- F3B direct curves by production file span & horse-race proof
def fig3b():
    fig, axes = plt.subplots(1, 3, figsize=(15.6, 4.65), gridspec_kw=dict(width_ratios=[1.05, 1.02, 1.08], wspace=0.36))
    fc = DS["file_span_curves"]

    # Panel 1: Full sample re-plotted along actual modified production files (0 -> 1 -> 2 -> 3-5 -> >=6)
    ax = axes[0]
    df_all = pd.DataFrame(fc["all_smells"])
    x = np.arange(5)
    for m in MODELS:
        sub = df_all[df_all.model == m]
        ys = [0.0] + [r["tokens"][0] for _, r in sub.iterrows()]
        lo = [0.0] + [r["tokens"][1] for _, r in sub.iterrows()]
        hi = [0.0] + [r["tokens"][2] for _, r in sub.iterrows()]
        ax.plot(x, ys, "-o", color=COL[m], lw=2.3, ms=6.2, label=MODEL_SHORT[m])
        ax.fill_between(x, lo, hi, color=COL[m], alpha=0.11, lw=0)
        dy = 1.8 if m == "glm" else (-1.9 if m == "deepseek" else 0.0)
        ax.text(4.08, ys[-1] + dy, f"+{ys[-1]:.0f}%", va="center", fontsize=8.9, color=COL[m], weight="bold")
    ax.axhline(0, color=MUTED, ls="--", lw=1)
    ax.text(0.12, 47.5, "S0–S2 内改动文件数被锁死；\n改按真实文件数展开后，\n三模型开销全线单调递增",
            ha="left", va="center", fontsize=8.3, color="#1b4f72",
            bbox=dict(boxstyle="round,pad=0.26", fc="#f2f7fb", ec="#85c1e9", lw=0.75))
    ax.set_xticks(x, ["干净代码\n(0 文件)", "1 个文件\n(n≈755)", "2 个文件\n(n≈441)", "3–5 个文件\n(n≈666)", "≥6 个文件\n(n≈547)"], fontsize=8.5)
    ax.set_xlim(-0.18, 4.58)
    ax.set_ylim(-4, 58)
    ax.set_ylabel("总 Token 增幅 (%)")
    ax.set_xlabel("补丁实际改动的生产文件数（全样本 7,223 组）", fontsize=8.8, color=MUTED)
    ax.set_title("① 按“改动生产文件数”重画：全线单调上升", loc="left", fontsize=11.1)
    ax.legend(loc="upper right", fontsize=8.6)

    # Panel 2: Within Feature Envy — 1 file (intra-file) vs 2 files vs >=3 files + static RAD>=3 truncation note
    ax = axes[1]
    df_fe = pd.DataFrame(fc["fe_by_files"])
    xf = np.arange(3)
    ax.axvspan(-0.18, 1.0, color="#eafaf1", zorder=0)
    for m in MODELS:
        sub = df_fe[df_fe.model == m]
        ys = [r["tokens"][0] for _, r in sub.iterrows()]
        lo = [r["tokens"][1] for _, r in sub.iterrows()]
        hi = [r["tokens"][2] for _, r in sub.iterrows()]
        ax.plot(xf, ys, "-o", color=COL[m], lw=2.3, ms=6.3, label=MODEL_SHORT[m])
        ax.fill_between(xf, lo, hi, color=COL[m], alpha=0.10, lw=0)
    ax.axhline(0, color=MUTED, ls="--", lw=1)
    ax.annotate("同文件内（1 文件）：\nGPT 零损耗 (-0.4%)", xy=(0.0, -0.4), xytext=(0.06, -11.5),
                fontsize=8.2, color=COL["gpt"], weight="bold", arrowprops=dict(arrowstyle="->", color=COL["gpt"], lw=0.9))
    ax.annotate("跨出第 2 个文件：\nGLM 跃升至 +30.7%\nGPT 跃升至 +7.6%", xy=(1.0, 30.7), xytext=(0.92, 39.5),
                fontsize=8.1, color=COL["glm"], weight="bold", arrowprops=dict(arrowstyle="->", color=COL["glm"], lw=0.9))
    ax.text(1.0, 53.5, "注：提示词锁死静态 RAD ≥3（缺 1–2 文件样本），切掉了左端爬坡区",
            ha="center", va="center", fontsize=7.8, color="#a04000",
            bbox=dict(boxstyle="round,pad=0.22", fc="#fff8f2", ec="#e59866", lw=0.7))
    ax.set_xticks(xf, ["1 个文件\n(同文件内搬移)", "2 个文件\n(双文件跨类)", "≥3 个文件\n(多文件委托)"], fontsize=8.7)
    ax.set_xlim(-0.22, 2.25)
    ax.set_ylim(-16, 59)
    ax.set_ylabel("依恋情结内总 Token 增幅 (%)")
    ax.set_xlabel("依恋情结改动的生产文件数（控制单一坏味类型）", fontsize=8.8, color=MUTED)
    ax.set_title("② 同类坏味内：1→2 个文件是核心跃升点", loc="left", fontsize=11.1)

    # Panel 3: Within-same-task multivariate horse-race regression (Surface S0-S2 vs 3 Deep Structural Factors)
    ax = axes[2]
    hr = DS["within_task_horserace"]
    factors = [
        ("lv", "表面严重度档位\n(S0→S1→S2)"),
        ("files", "改动生产文件数\n(跨文件跨度)"),
        ("cf", "新增控制流分支\n(函数内复杂度)"),
        ("ent", "核心故障点纠缠\n(脱离数据/混融)"),
    ]
    ax.axhspan(-0.46, 0.46, color="#f0f2f5", zorder=0)
    bh = 0.22
    for j, m in enumerate(MODELS):
        for i, (fk, _) in enumerate(factors):
            d_m = hr[m][fk]
            v = d_m["multi_pct"]
            p = d_m["multi_p"]
            y = i + (j - 1) * (bh + 0.02)
            ax.barh(y, v, height=bh, color="#b0b8c1" if fk == "lv" else COL[m], alpha=0.88, edgecolor="white")
            star = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))
            if fk != "lv" and (v >= 2.3 or star):
                ax.text(v + 0.14, y, f"+{v:.1f}%{star}", va="center", ha="left", fontsize=7.9, color=COL[m], weight="bold")
    ax.text(1.75, 0.0, "控制底层变量后\nS0–S2 净效应归零\n(三模型 p > 0.38)", va="center", ha="left", fontsize=8.2, color="#566573", weight="bold")
    ax.axvline(0, color=INK, lw=0.85)
    ax.set_yticks(range(4), [f[1] for f in factors], fontsize=8.7)
    ax.invert_yaxis()
    ax.set_xlim(-0.8, 6.2)
    ax.set_xlabel("同题多变量回归：每 +1 标准差的净 Token 增幅 (%)", fontsize=8.6, color=MUTED)
    ax.set_title("③ 同题回归比拼：三大底层量完胜表面分档", loc="left", fontsize=11.1)

    title(fig, "图 3  换对横轴见真相：按“改动生产文件数”重画曲线呈清晰单调上升，同题回归证实底层结构量才是真因",
          "左：全样本按实际改动生产文件数单调爬升；中：同文件到双文件是起跳拐点；右：控制原题后表面 S0–S2 档位净效应趋零 (* p<0.05, ** p<0.01, *** p<0.001)")
    fig.savefig(STATE["out"] / "fig3b_driver_curves.png")
    plt.close(fig)


# ---------------------------------------------------------------- F3 controlled-variable decomposition (3 panels)
def fig3():
    fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.5), gridspec_kw=dict(width_ratios=[1.0, 1.05, 1.05], wspace=0.28))

    # Left: Injection invariant (RAD locked at S0) vs physical code size growth
    ax = axes[0]
    tp = DS["topology_by_level"]
    x = np.arange(4)
    rad_f = [1.0] + [tp[f"GC|{lv}"]["rad_files"] for lv in LEVELS]
    rad_m = [1.0] + [tp[f"GC|{lv}"]["rad_modules"] for lv in LEVELS]
    vol_k = [0.0] + [tp[f"GC|{lv}"]["added_lines"] / 1000.0 for lv in LEVELS]
    ax.plot(x, rad_f, "-s", color="#c0392b", lw=2.3, ms=6.5, label="波及文件数（S0–S2 不变量）")
    ax.plot(x, rad_m, "-^", color="#2980b9", lw=2.1, ms=6.5, label="跨模块数（S0–S2 不变量）")
    ax.plot(x, vol_k, "--o", color="#7f8c8d", lw=1.8, ms=5.8, label="物理新增行数（千行，涨 5 倍）")
    for xi, (rf, vk) in enumerate(zip(rad_f, vol_k)):
        if xi > 0:
            ax.text(xi, rf + 0.36, f"{int(rf)} 文件", ha="center", fontsize=8.4, color="#c0392b", weight="bold")
            ax.text(xi, vk - 0.68 if xi == 1 else vk + 0.42, f"{vk:.1f}k", ha="center", fontsize=8.3, color="#555")
    ax.axvspan(-0.15, 1.0, color="#fdf1e6", zorder=0)
    ax.set_xticks(x, ["干净代码", "S0 轻度", "S1 中度", "S2 重度"], fontsize=9)
    ax.set_ylim(-0.8, 10.6)
    ax.set_ylabel("拓扑跨度（个） / 新增体量（千行）")
    ax.set_title("① 注入协议：拓扑破界在 S0 已锁定", loc="left", fontsize=11.3)
    ax.legend(loc="upper left", fontsize=8.2)
    ax.text(0.45, 4.9, "破界在 S0\n一步到位", ha="center", fontsize=8.4, color="#b5651d")

    # Middle: Actual characters read by Agent from injected files (window shielding vs mandatory reading)
    ax = axes[1]
    rs = DS["controlled_variables"]["read_saturation"]
    xl = np.arange(3)
    sm_spec = [
        ("GC", "上帝类（并列堆方法 → 窗口屏蔽封顶）", SCOL["GC"], "s"),
        ("LM", "长方法（塞进必经流 → 多读量翻 5 倍）", SCOL["LM"], "^"),
        ("FE", "依恋情结（单方法搬迁 → 仅差 19 行）", SCOL["FE"], "o"),
    ]
    for sm, lab, col, mk in sm_spec:
        ys_gpt = [rs[f"gpt|{sm}|{lv}"]["delta_chars_med"] / 1000.0 for lv in LEVELS]
        ys_glm = [rs[f"glm|{sm}|{lv}"]["delta_chars_med"] / 1000.0 for lv in LEVELS]
        ax.plot(xl, ys_gpt, f"-{mk}", color=col, lw=2.2, ms=6.2, label=lab)
        ax.plot(xl, ys_glm, f"--{mk}", color=col, lw=1.6, ms=5.2, alpha=0.65)
    ax.annotate("长方法：多读量涨 5.1 倍\n（GPT +1.9k → +9.6k）", xy=(1.96, 9.5), xytext=(0.48, 9.2),
                fontsize=8.2, color=SCOL["LM"], weight="bold", arrowprops=dict(arrowstyle="->", color=SCOL["LM"]))
    ax.annotate("上帝类物理涨 5 倍，GPT 多读\n稳定在 4.3k～5.0k（窗口封顶）", xy=(0.85, 4.35), xytext=(0.02, 6.2),
                fontsize=8.1, color=SCOL["GC"], arrowprops=dict(arrowstyle="->", color=SCOL["GC"]))
    ax.set_xticks(xl, ["S0 轻度", "S1 中度", "S2 重度"])
    ax.set_xlim(-0.2, 2.25)
    ax.set_ylim(0, 19.2)
    ax.set_ylabel("实际多读入受污染字符数（千字符，中位数）")
    ax.set_xlabel("实线 = GPT  ｜  虚线 = GLM", fontsize=8.8, color=MUTED)
    ax.set_title("② 视野过滤：并列方法被屏蔽，内联必读", loc="left", fontsize=11.3)
    ax.legend(loc="upper left", fontsize=8.0)

    # Right: Universal control-flow branch complexity (cf_added) across ALL 7,223 pairs!
    ax = axes[2]
    bb = pd.DataFrame(DS["branch_bins"])
    blabs = ["≤15\n轻度", "16–45\n中度", "46–150\n高度", ">150\n密集"]
    xb = np.arange(4)
    for m in MODELS:
        sub = bb[bb.model == m]
        vals = np.array(sub.tokens.tolist())
        ax.plot(xb, vals[:, 0], "-o", color=COL[m], lw=2.2, ms=6.2, label=MODEL_SHORT[m])
        ax.fill_between(xb, vals[:, 1], vals[:, 2], color=COL[m], alpha=0.11, lw=0)
        off = 1.7 if m == "glm" else (-1.7 if m == "deepseek" else 0.0)
        ax.text(3.08, vals[-1, 0] + off, f"+{vals[-1, 0]:.0f}%", va="center", fontsize=9.0, color=COL[m], weight="bold")
    ax.axhline(0, color=MUTED, ls="--", lw=1)
    ax.set_xticks(xb, blabs, fontsize=9)
    ax.set_xlim(-0.2, 3.52)
    ax.set_ylim(-3, 58)
    ax.set_ylabel("总 Token 增幅 (%)")
    ax.set_xlabel("补丁新增控制流分支数（全样本统一分箱）", fontsize=8.8, color=MUTED)
    ax.set_title("③ 有效复杂度：控制流分支驱动持续爬升", loc="left", fontsize=11.3)
    ax.legend(loc="upper left", fontsize=8.8, ncol=3)

    title(fig, "图 4  控制变量拆解：为什么“有坏味就耗 Token，但加重坏味却少见涨价”？",
          "注入协议在 S0 已锁死跨模块耦合不变量（左）；类内横向堆并列方法被局部读取窗口屏蔽，唯有塞入必经控制流的分支持续推高阅读与推理负担（中、右）")
    fig.savefig(STATE["out"] / "fig3_topology_vs_complexity.png")
    plt.close(fig)


# ---------------------------------------------------------------- F4 four trajectory stages (NEW COGNITIVE ANATOMY)
def fig4():
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 4.4), gridspec_kw=dict(width_ratios=[1.25, 1], wspace=0.30))

    # Left: Step deltas across Stage 1 (Nav), Stage 2 (Logic Slicing), Stage 4 (Post-edit Verification/Rework)
    ax = axes[0]
    fs = DS["four_stages"]
    stage_keys = [("nav_steps", "① 入口检索\n（找到目标文件前）"),
                  ("slice_steps", "② 局部逻辑剥离\n（读文件 → 首次修改）"),
                  ("post_steps", "④ 契约验证与返工\n（首次修改之后）")]
    width = 0.24
    for i, (sk, _) in enumerate(stage_keys):
        for j, m in enumerate(MODELS):
            v, lo, hi = fs[f"{m}|ALL"][sk]
            xpos = i + (j - 1) * (width + 0.02)
            ax.bar(xpos, v, width, color=COL[m], alpha=0.85, edgecolor="white")
            ax.errorbar(xpos, v, yerr=[[v - lo], [hi - v]], fmt="none", ecolor=INK, capsize=3, lw=1.1)
            off = 0.14 if v >= 0 else -0.14
            ax.text(xpos, (hi if v >= 0 else lo) + off, f"{v:+.2f}", ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=8.6, color=COL[m], weight="bold" if sk == "slice_steps" else "normal")
    ax.axhline(0, color=INK, lw=0.8)
    ax.axvspan(0.55, 1.45, color="#fdf1e6", zorder=0)
    ax.set_xticks(range(3), [s[1] for s in stage_keys], fontsize=9.5)
    ax.set_ylim(-0.75, 3.45)
    ax.set_ylabel("平均增减步数（有坏味 − 干净代码）")
    ax.set_title("步数花在哪：找文件不慢，卡在进门后的逻辑剥离与返工", loc="left")
    ax.legend(handles=[Patch(color=COL[m], label=MODEL_SHORT[m]) for m in MODELS], loc="upper left", fontsize=9, ncol=3)

    # Right: Stage 3 — Structured edit anchor failure rate (oldString not found / ambiguous matches)
    ax = axes[1]
    width = 0.30
    for i, m in enumerate(MODELS):
        b = fs[f"{m}|ALL"]["edit_err_base"]
        v = fs[f"{m}|ALL"]["edit_err_smell"]
        dv, _, _ = fs[f"{m}|ALL"]["edit_err_diff_pp"]
        ax.bar(i - width / 2 - 0.02, b, width, color="#cfd6de", edgecolor="white", label="干净代码" if i == 0 else "")
        ax.bar(i + width / 2 + 0.02, v, width, color=COL[m], alpha=0.88, edgecolor="white", label="注入坏味后" if i == 0 else "")
        ax.text(i - width / 2 - 0.02, b + 0.3, f"{b:.1f}%", ha="center", fontsize=8.8, color=MUTED)
        ax.text(i + width / 2 + 0.02, v + 0.3, f"{v:.1f}%", ha="center", fontsize=9.2, color=COL[m], weight="bold")
        if dv > 1.0:
            ax.text(i, max(b, v) + 1.55, f"报错率 ×{v / b:.1f} 倍", ha="center", fontsize=9.2, color="#c0392b", weight="bold")
    ax.set_xticks(range(3), [MODEL_SHORT[m] for m in MODELS])
    ax.set_ylim(0, 14.5)
    ax.set_ylabel("出现编辑匹配报错的任务占比 (%)")
    ax.set_title("③ 落笔编辑：复杂缩进与重复块使弱模型匹配报错翻倍", loc="left")
    ax.legend(loc="upper left", fontsize=9)

    title(fig, "图 5  执行轨迹四阶段解剖：坏味并未阻碍文件定位，而是击穿了“逻辑剥离、落笔匹配与修改返工”",
          "基于 9,684 条轨迹拆解；编辑匹配报错主要源于深层嵌套缩进失配与内联重复代码导致的上下文多义碰撞")
    fig.savefig(STATE["out"] / "fig4_four_stages.png")
    plt.close(fig)


# ---------------------------------------------------------------- F5 context carry-over accounting
ACC_LABEL = [("inj_read", "受污染代码被读入并在后续轮次反复重算", "#c0392b"),
             ("other_read", "跨文件追查其他源码", "#e9a03b"),
             ("overhead", "步数增加带来的固定提示词开销", "#7f8c8d"),
             ("gen_carried", "模型推理与输出增长", "#5b4b9a"),
             ("test_build", "测试与构建输出", "#3b75af"),
             ("other_tool", "补丁修改与其他工具", "#95a5a6")]


def fig5():
    fig, ax = plt.subplots(figsize=(12.2, 5.4))
    sm_cn = {"FE": "依恋情结", "GC": "上帝类", "LM": "长方法"}
    rows = []
    for m in MODELS:
        for s in SMELLS:
            rows.append((f"{MODEL_SHORT[m]} · {sm_cn[s]}", R["accounting"][f"{m}|{s}"]))
        rows.append((f"{MODEL_SHORT[m]} · 汇总", R["accounting"][f"{m}|ALL"]))
    y = np.arange(len(rows))[::-1].astype(float)
    for i in range(len(rows)):
        if i % 4 == 3:
            y[i + 1:] -= 0.6
    for yi, (lab, d) in zip(y, rows):
        pos = neg = 0.0
        for key, _, col in ACC_LABEL:
            v = d["contrib_pp"][key] + (d["contrib_pp"]["gen"] if key == "gen_carried" else 0)
            if v >= 0:
                ax.barh(yi, v, left=pos, color=col, height=0.72, edgecolor="white", lw=0.5)
                pos += v
            else:
                ax.barh(yi, v, left=neg, color=col, height=0.72, edgecolor="white", lw=0.5)
                neg += v
        share = d["contrib_pp"]["inj_read"] / d["extra_over_base"] if d["extra_over_base"] > 0 else np.nan
        ax.text(pos + 0.5, yi, f"净增 +{d['extra_over_base']:.1f}%（坏味代码重算占 {share:.0%}）", va="center", fontsize=8.8,
                color=INK, weight="bold" if "汇总" in lab else None)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=9.5)
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlabel("相对干净代码总 Token 的增量拆解（百分点）")
    ax.set_xlim(-6, 52)
    ax.legend(handles=[Patch(color=c, label=l) for _, l, c in ACC_LABEL], loc="upper center", bbox_to_anchor=(0.46, -0.10),
              fontsize=9.0, ncol=3)
    title(fig, "图 6  上下文复利放大效应：一次读入的低内聚/高混杂代码，会在后续每一轮推理中被重复计费",
          "按每轮新增上下文来源精确拆解（拟合优度 R²=0.95–0.96）；测试与构建输出几乎不产生额外消耗")
    fig.savefig(STATE["out"] / "fig5_token_accounting.png")
    plt.close(fig)


# ---------------------------------------------------------------- F6 three structural degradations -> observable behaviors
def fig6():
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), gridspec_kw=dict(wspace=0.30))

    # Panel 1: Cohesion collapse -> single read brings 6-8x irrelevant code
    ax = axes[0]
    sr = R["mechanism"]["same_request_ratio"]
    width = 0.25
    sm_cn = {"FE": "数据–行为分离", "GC": "职责混杂（低内聚）", "LM": "控制流内联"}
    for j, s in enumerate(SMELLS):
        for i, m in enumerate(["glm", "deepseek"]):
            vals = [sr.get(f"{m}|{s}|{lv}", {}).get("median_x", np.nan) for lv in LEVELS]
            ax.bar(np.arange(3) + (j - 1) * width + (i - 0.5) * width / 2, vals, width / 2, color=SCOL[s],
                   alpha=0.95 if i == 0 else 0.55, edgecolor="white")
    ax.set_xticks(range(3), ["S0 轻度", "S1 中度", "S2 重度"])
    ax.set_ylabel("相同读取请求返回的源码倍数")
    ax.axhline(1, color=MUTED, ls="--", lw=1)
    ax.set_ylim(0, 10.5)
    ax.set_title("职责混杂：同一次读取涌入 6–8 倍异质代码", loc="left")
    ax.legend(handles=[Patch(color=SCOL[s], label=sm_cn[s]) for s in SMELLS] +
              [Patch(color="#777", label="深色 GLM / 浅色 DeepSeek")], fontsize=8.3, loc="upper left")

    # Panel 2: Data-behavior separation -> cross-host dual lookup
    ax = axes[1]
    bo = R["mechanism"]["fe_both_owners"]
    for i, m in enumerate(MODELS):
        b = np.mean([bo[f"{m}|{lv}"]["base"] for lv in LEVELS]) * 100
        v = [bo[f"{m}|{lv}"]["smell"] * 100 for lv in LEVELS]
        ax.bar(i - 0.3, b, 0.18, color="#cfd6de")
        for j in range(3):
            ax.bar(i - 0.1 + 0.2 * j, v[j], 0.18, color=COL[m], alpha=0.5 + 0.25 * j)
        ax.text(i + 0.1, max(v) + 3, f"{b:.0f}% → {np.mean(v):.0f}%", ha="center", color=COL[m], weight="bold", fontsize=9.8)
    ax.set_xticks(range(3), [MODEL_SHORT[m] for m in MODELS])
    ax.set_ylim(0, 95)
    ax.set_ylabel("同时核对原宿主与新宿主文件的比例 (%)")
    ax.set_title("数据–行为分离：被迫跨双端追踪状态与契约", loc="left")
    ax.text(1, 88, "灰色 = 干净代码；彩色 = S0 / S1 / S2", ha="center", fontsize=8.5, color=MUTED)

    # Panel 3: Control-flow elongation -> multi-window slicing pagination
    ax = axes[2]
    mw = R["mechanism"]["lm_multi_window"]
    for m in ["gpt", "glm"]:
        base = np.mean([mw[f"{m}|{lv}"]["base"] for lv in LEVELS]) * 100
        ys = [base] + [mw[f"{m}|{lv}"]["smell"] * 100 for lv in LEVELS]
        ax.plot(range(4), ys, "-o", color=COL[m], lw=2.2, label=MODEL_SHORT[m])
        ax.text(3.08, ys[-1], f"{ys[-1]:.0f}%", color=COL[m], va="center", weight="bold")
    ax.set_xticks(range(4), LEVEL_LABEL["LM"], fontsize=9)
    ax.set_xlim(-0.15, 3.4)
    ax.set_ylim(0, 75)
    ax.set_ylabel("首次修改前多段翻页读取目标文件的比例 (%)")
    ax.set_title("控制流拉长：目标语句超出单屏被迫连续翻页", loc="left")
    ax.legend(loc="upper left", fontsize=9)
    ax.text(1.5, 6, "注：DeepSeek 主要用命令行读取，不计入此项", fontsize=8.2, color=MUTED, ha="center")

    title(fig, "图 7  三大底层逻辑退化的行为指纹：信噪比稀释、双端契约追踪与单屏切片截断")
    fig.savefig(STATE["out"] / "fig6_mechanisms.png")
    plt.close(fig)


# ---------------------------------------------------------------- F7 fault-site entanglement vs adjacent noise (NEW DEEP PROOF)
def fig7():
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.3), sharey=True, gridspec_kw=dict(wspace=0.18))
    fe = DS["fault_entanglement"]
    specs = [("FE", "数据–行为分离（依恋情结）",
              "周边方法移位（故障仍在原宿主）", "故障方法自身移位（行为脱离数据宿主）"),
             ("GC", "异质职责混杂（上帝类）",
              "仅混入周边异质职责", "故障逻辑与迁入职责发生结构纠缠")]
    width = 0.30
    for ax, (sm, ttl, lab0, lab1) in zip(axes, specs):
        for i, m in enumerate(MODELS):
            v0, lo0, hi0 = fe[f"{m}|{sm}|0"]["tokens"]
            v1, lo1, hi1 = fe[f"{m}|{sm}|1"]["tokens"]
            ax.bar(i - width / 2 - 0.02, max(v0, 0), width, color="#b8c4ce", edgecolor="white")
            ax.errorbar(i - width / 2 - 0.02, v0, yerr=[[v0 - lo0], [hi0 - v0]], fmt="none", ecolor=MUTED, capsize=3, lw=1)
            ax.bar(i + width / 2 + 0.02, max(v1, 0), width, color=COL[m], alpha=0.90, edgecolor="white")
            ax.errorbar(i + width / 2 + 0.02, v1, yerr=[[v1 - lo1], [hi1 - v1]], fmt="none", ecolor=INK, capsize=3, lw=1.1)
            ax.text(i - width / 2 - 0.02, max(hi0, 0) + 1.8, f"{v0:+.1f}%", ha="center", fontsize=8.8, color="#4b5663")
            ax.text(i + width / 2 + 0.02, max(hi1, 0) + 1.8, f"{v1:+.1f}%", ha="center", fontsize=9.2, color=COL[m], weight="bold")
        ax.axhline(0, color=MUTED, ls="--", lw=1)
        ax.set_xticks(range(3), [MODEL_SHORT[m] for m in MODELS])
        ax.set_ylim(-9, 76)
        ax.set_title(ttl, loc="left")
        ax.text(-0.46, 72, f"■ 浅灰：{lab0}\n■ 彩色：{lab1}", ha="left", va="top", fontsize=8.3, color=MUTED)
    axes[0].set_ylabel("总 Token 增幅 (%)")
    axes[0].annotate("故障点未脱离数据宿主时\nGPT 几乎零损耗（+0.4%）", xy=(-0.17, 2.0), xytext=(-0.48, 36),
                     fontsize=8.6, color=INK, arrowprops=dict(arrowstyle="->", color=MUTED))
    title(fig, "图 8  决定性分水岭：坏味是“停留在周边”，还是“直接拆散了故障点的数据与逻辑契约”？",
          "按注入补丁是否触动故障核心逻辑分组；同一原题内对比下，故障方法脱离数据宿主使 GPT 额外增加 +8.7%（95% CI +2.6%～+16.8%）")
    fig.savefig(STATE["out"] / "fig7_fault_entanglement.png")
    plt.close(fig)


# ---------------------------------------------------------------- F8 control-flow knee & premature convergence
def fig8():
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 4.5), gridspec_kw=dict(width_ratios=[1.15, 1], wspace=0.30))

    # Left: Control-flow / method span knee
    ax = axes[0]
    bins = pd.DataFrame(R["mechanism"]["lm_bins"])
    labels = ["60–120\n(嵌套3–4)", "120–160\n(嵌套5–6)", "160–200\n(超单屏)", "200–240\n(深层分支)", "240–320\n(嵌套7–8)", "320–480\n(巨型流程)"]
    x = np.arange(len(labels))
    for m in MODELS:
        b = bins[bins.model == m]
        t = np.array(b.tokens.tolist())
        ax.plot(x, t[:, 0], "-o", color=COL[m], lw=2.1, label=MODEL_SHORT[m])
        ax.fill_between(x, t[:, 1], t[:, 2], color=COL[m], alpha=0.10, lw=0)
    ax.axvspan(1.5, 3.5, color="#fdecea", zorder=0)
    ax.axhline(0, color=MUTED, ls="--", lw=1)
    ax.set_xticks(x, labels, fontsize=8.6)
    ax.set_ylim(-14, 73)
    ax.set_ylabel("总 Token 增幅 (%)")
    ax.set_xlabel("内联后的方法有效行数与典型控制流嵌套层数", fontsize=9, color=MUTED)
    ax.set_title("控制流跨度突破单次读取窗口（~160 行）时出现拐点", loc="left")
    ax.legend(loc="upper left", fontsize=9, ncol=3)
    ax.text(2.5, 55, "感知截断临界区\nGPT 由 +2.5% 跃升至 +13.1%", ha="center", fontsize=8.8, color="#a93226")

    # Right: Premature convergence failure mode
    ax = axes[1]
    fm = R["success"]["failure_mode"]
    items = [("总 Token 投入", fm["tokens"]), ("交互推理步数", fm["steps"])]
    for i, (lab, (v, lo, hi)) in enumerate(items):
        ax.barh(i, v, color="#c0392b", alpha=0.82, height=0.46)
        ax.errorbar(v, i, xerr=[[v - lo], [hi - v]], color=INK, capsize=4)
        ax.text(lo - 0.8, i, f"{v:.0f}%", ha="right", va="center", fontsize=10.5, color="#c0392b", weight="bold")
    v, lo, hi = fm["tests"]
    ax.text(-27.5, 1.95, f"回归测试执行次数：失败时平均少跑 {-v:.2f} 次（区间 {-hi:.2f}～{-lo:.2f}）\n"
            f"代码修改次数：平均少改 {-fm['edits'][0]:.2f} 次（只修表层报错便提前结束）",
            fontsize=9.2, color="#2c5282", va="center")
    ax.set_yticks(range(2), [it[0] for it in items])
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_xlim(-29, 5)
    ax.set_ylim(2.55, -0.55)
    ax.set_xlabel("同一道原题内：未通过变体 − 通过变体")
    ax.set_title(f"深层控制流遮蔽下的失败模式：过早收敛（{fm['tasks']} 道分化原题）", loc="left")

    title(fig, "图 9  控制流复杂度的双重后果：轻则跨屏翻页推高成本，重则淹没深层根因诱发“治标不治本”",
          "左：同一 S1 批次内 ≤160 行仅 +1.2%，>160 行跃升至 +15.4%；右：辅助函数被内联压平后，AI 易修完表层异常即停机（Wilcoxon p<0.002）")
    fig.savefig(STATE["out"] / "fig8_complexity_knee_and_failure.png")
    plt.close(fig)


# ---------------------------------------------------------------- F9 tail risk & task difficulty
def fig9():
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 4.2), gridspec_kw=dict(wspace=0.28))

    # Left: Tail risk (>=2x cost explosion)
    ax = axes[0]
    width = 0.2
    for i, m in enumerate(MODELS):
        t = R["tail"][m]
        nv, nlo, nhi = t["noise_p2.0"]
        ax.bar(i - 1.5 * width, nv, width, color="#cfd6de", edgecolor="white")
        ax.errorbar(i - 1.5 * width, nv, yerr=[[nv - nlo], [nhi - nv]], color=MUTED, capsize=3, lw=1)
        for j, lv in enumerate(LEVELS):
            v, lo, hi = t[f"{lv}_p2.0"]
            ax.bar(i + (j - 0.5) * width, v, width, color=COL[m], alpha=0.45 + 0.25 * j, edgecolor="white")
            ax.errorbar(i + (j - 0.5) * width, v, yerr=[[v - lo], [hi - v]], color=INK, capsize=2, lw=0.8)
        v = t["ALL_p2.0"][0]
        top_y = max([nhi] + [t[f"{lv}_p2.0"][2] for lv in LEVELS])
        ax.text(i, top_y + 1.5, f"正常波动的 {v / nv:.1f} 倍", ha="center", fontsize=9.0, weight="bold", color=COL[m])
    ax.set_xticks(range(3), [MODEL_SHORT[m] for m in MODELS])
    ax.set_ylim(0, 44)
    ax.set_ylabel("Token 翻倍（≥2×）的任务占比 (%)")
    ax.set_title("轻量模型在坏味区出现“成本翻倍”的频率激增", loc="left")
    ax.legend(handles=[Patch(color="#cfd6de", label="干净代码重跑波动"),
                       Patch(color="#555", alpha=0.45, label="S0"), Patch(color="#555", alpha=0.70, label="S1"),
                       Patch(color="#555", alpha=0.95, label="S2")], loc="upper left", fontsize=8.6, ncol=2)

    # Right: Difficulty terciles (fixed comprehension entry fee on simple tasks)
    ax = axes[1]
    qs = ["易", "中", "难"]
    for m in MODELS:
        rel = np.array([R["difficulty"][f"{m}|{q}"]["rel"] for q in qs])
        ax.plot(range(3), rel[:, 0], "-o", color=COL[m], lw=2.2, label=MODEL_SHORT[m])
        ax.fill_between(range(3), rel[:, 1], rel[:, 2], color=COL[m], alpha=0.10)
    ax.set_xticks(range(3), ["简单任务", "中等任务", "复杂任务"])
    ax.set_xlabel("任务本身难度（由其余两个模型在干净代码上的消耗划分）", fontsize=9, color=MUTED)
    ax.set_ylabel("相对 Token 增幅 (%)")
    ax.axhline(0, color=MUTED, ls="--")
    ax.set_title("日常简单小改动被坏味放大的比例最高", loc="left")
    ax.legend(loc="upper right", fontsize=9)
    ax.text(1.32, 13.8, "GPT 在三档难度上固定多花约 2.5 万 Token\n（相当于固定的代码理解门槛）", ha="center", fontsize=8.4, color=COL["gpt"])
    ax.set_ylim(-5, 58)

    title(fig, "图 10  脆弱性分布：轻量模型面临近 3 倍超支爆表风险，日常高频小需求受固定理解门槛拖累最深")
    fig.savefig(STATE["out"] / "fig9_tail_and_difficulty.png")
    plt.close(fig)


# ---------------------------------------------------------------- F10 batch validity check
def fig10():
    fig, ax = plt.subplots(figsize=(10.8, 4.3))
    keys = [("steps_to_contact", "首次读到坏味文件前的步数"),
            ("tokens_before_contact", "首次读到坏味文件前的 Token"),
            ("out_per_step_before", "读到坏味文件前的单步输出量"),
            ("out_per_step_after", "读到坏味文件后的单步输出量"),
            ("total_tokens_same_subset", "全程总 Token 变化（对照）")]
    for j, m in enumerate(MODELS):
        nc = R["negative_control"][m]
        for i, (k, _) in enumerate(keys):
            v, lo, hi = nc[k]
            y = i + (j - 1) * 0.22
            ax.errorbar(v, y, xerr=[[v - lo], [hi - v]], fmt="o", color=COL[m], capsize=3, lw=1.8, ms=6)
    ax.set_yticks(range(len(keys)), [k[1] for k in keys])
    ax.axvline(0, color=MUTED, ls="--")
    ax.axhspan(-0.5, 2.5, color="#eef6ee", zorder=0)
    ax.text(19, 0.35, "尚未接触坏味代码时：三模型行为零差异\n→ 排除分批运行的服务端波动假说", fontsize=9.5, color="#2e7d32")
    ax.invert_yaxis()
    ax.set_xlabel("相对干净代码的变化 (%)，95% 置信区间")
    legend_models(ax, loc="center right", bbox_to_anchor=(1.0, 0.42), fontsize=9)
    title(fig, "图 11  因果归因检验：在智能体首次读到受污染源码之前，各批次运行轨迹完全一致",
          "针对 S2→S1→S0→干净代码 分批执行的时间差，以首次接触注入文件为分界点进行前后对照验证")
    fig.savefig(STATE["out"] / "fig10_validity.png")
    plt.close(fig)


# ---------------------------------------------------------------- F11 deep governance map
def fig11():
    fig, axes = plt.subplots(3, 1, figsize=(12.4, 6.3), gridspec_kw=dict(hspace=1.25))
    spec = [
        ("维度一：职责分离度与类内聚（表象：上帝类）", "#c0392b",
         [0, 1, 3, 7, 12], [(0, 1, "#d5efd8", "单一职责"),
                            (1, 3, "#fff3cd", "边界模糊预警"),
                            (3, 12, "#f8d7da", "必须剥离异质职责、恢复边界（仅把大类拆小几乎不省成本）")],
         "混入外部职责源数 / 跨模块波及文件数",
         "混入 ≥3 个外部职责（TCC < 0.2）成本即饱和；治理核心是恢复内聚"),
        ("维度二：数据–行为局部性（表象：依恋情结）", "#3b75af",
         [0, 30, 70, 100], [(0, 30, "#d5efd8", "行为留在数据宿主内"),
                            (30, 100, "#f8d7da", "将核心逻辑迁回状态持有类（消除双端核对与契约误伤）")],
         "方法访问外部类属性占比（1 − LAA，%）",
         "热点逻辑脱离数据宿主后双端核对率翻倍；应按职责归属而非调用次数治理"),
        ("维度三：局部控制流复杂度（表象：长方法）", "#2e8b57",
         [0, 120, 160, 240, 480], [(0, 120, "#d5efd8", "单屏可切片区（嵌套 ≤4 层）"),
                                   (120, 160, "#fff3cd", "临界区"),
                                   (160, 480, "#f8d7da", "提炼具名子函数（防跨屏截断、编辑失配与漏修深层根因）")],
         "函数有效行数（对应控制流圈复杂度 CC 10 → 80、嵌套 3 → 8 层）",
         "强模型 >160 行（嵌套 ≥5 层）成本跳升 5 倍；轻量模型 ≥60 行即受损"),
    ]
    for ax, (ttl, col, ticks, zones, xlab, note) in zip(axes, spec):
        hi = ticks[-1]
        for a, b, zcol, lab in zones:
            ax.axvspan(a, b, color=zcol)
            ax.text((a + b) / 2, 0.5, lab, ha="center", va="center", fontsize=9.6, color=INK,
                    weight="bold" if zcol == "#f8d7da" else "normal")
        ax.set_xlim(0, hi)
        ax.set_yticks([])
        ax.set_xticks(ticks)
        ax.grid(False)
        ax.set_title(ttl, loc="left", color=col, fontsize=11.5)
        ax.text(1.0, 1.08, note, ha="right", va="bottom", fontsize=9.0, color=MUTED, transform=ax.transAxes)
        ax.set_xlabel(xlab, fontsize=9, color=INK)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
    title(fig, "图 12  面向 AI 辅助开发的治理路线图：从“卡代码体积”转向“守职责边界、保数据局部、控分支深度”")
    fig.savefig(STATE["out"] / "fig11_governance.png")
    plt.close(fig)


# ---------------------------------------------------------------- F12 S1-S3 monotonic benchmark redesign
def fig12():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.8, 4.85), gridspec_kw=dict(wspace=0.24))

    # Left panel: Empirical S0-S2 distortion diagnosis
    xs = np.arange(4)
    lbl_map = {"GC": "上帝类 (GC)", "FE": "依恋情结 (FE)", "LM": "长方法 (LM)"}
    for s in ["GC", "FE", "LM"]:
        ys_glm = [0.0] + [cell("glm", s, lv)["tokens"][0] for lv in LEVELS]
        ys_gpt = [0.0] + [cell("gpt", s, lv)["tokens"][0] for lv in LEVELS]
        ax1.plot(xs, ys_glm, marker=MARK[s], color=SCOL[s], lw=2.4, ms=6.5, label=f"{lbl_map[s]} · GLM")
        ax1.plot(xs, ys_gpt, marker=MARK[s], color=SCOL[s], lw=1.35, ms=4.5, ls="--", alpha=0.72)

    ax1.axvspan(0, 1, color="#fbeee6", alpha=0.75, zorder=0)
    ax1.axhline(0, color=MUTED, lw=0.9, ls=":")
    ax1.text(0.46, 43.0, "① S0 锁死跨模块破界\n（波及 5–7 文件）\n起步即透支 68%–88%",
             ha="center", va="center", fontsize=8.4, color="#a04000", weight="bold",
             bbox=dict(boxstyle="round,pad=0.28", fc="#fff8f2", ec="#e59866", lw=0.8))
    ax1.annotate("② GC 末尾堆孤立方法被窗口屏蔽；\n>5k 行放弃翻页致 S2 反降",
                 xy=(2.0, 54.8), xytext=(2.12, 62.5), ha="center", va="bottom",
                 fontsize=8.5, color=SCOL["GC"], weight="bold",
                 arrowprops=dict(arrowstyle="->", color=SCOL["GC"], lw=1.0))
    ax1.text(2.36, 17.0, "③ FE 仅增只读属性（差 19 行）\n且三档独立选点（同单元仅 27%）",
             ha="center", va="center", fontsize=8.1, color=SCOL["FE"],
             bbox=dict(boxstyle="round,pad=0.24", fc="#f4f8fc", ec="#9bb8d3", lw=0.7))
    ax1.text(0.05, -5.8, "注：实线为轻量模型 GLM 实测均值，同色虚线为旗舰模型 GPT 实测均值", fontsize=8.0, color=MUTED)

    ax1.set_xticks(xs, ["干净代码", "S0\n现行轻度", "S1\n现行中度", "S2\n现行重度"])
    ax1.set_xlim(-0.12, 3.18)
    ax1.set_ylim(-8.5, 75)
    ax1.set_ylabel("相对干净代码的总 Token 增幅 (%)")
    ax1.set_title("现行 S0–S2 实测：起步阶跃、平台饱和与倒挂", loc="left")
    ax1.legend(loc="upper left", bbox_to_anchor=(0.0, 1.0), fontsize=8.3)

    # Right panel: Proposed S1-S3 nested monotonic design
    tiers = [
        (0.66, 1.34, "#eafaf1", "S1 局部感知层\n同模块 / 单屏内\n无共享状态冲突", 9.5),
        (1.66, 2.34, "#fef9e7", "S2 跨界消歧层\n跨模块双向耦合\n突破 160 行窗口", 29.0),
        (2.62, 3.30, "#fdedec", "S3 契约与根因交织\n多跳共享容器 / 路径纠缠\n抹路标（GC <3.8k 行）", 53.0),
    ]
    for x0, x1, fc, txt, ty in tiers:
        ax2.axvspan(x0, x1, color=fc, zorder=0)
        ax2.text((x0 + x1) / 2, ty, txt, ha="center", va="center", fontsize=8.0, color=INK, alpha=0.92)

    design_curves = {
        "LM": ([0, 24, 58, 100], "长方法：单屏内展开 → 跨屏截断 → 抹除路标+深层嵌套"),
        "GC": ([0, 29, 64, 94], "上帝类：邻接隔离 → 共享字段+同名词 → 待修路径直接纠缠"),
        "FE": ([0, 26, 52, 87], "依恋情结：同包只读 → 跨模块读写 → 多跳链+共享容器契约"),
    }
    for s in ["LM", "GC", "FE"]:
        ys, lab = design_curves[s]
        ax2.plot(xs, ys, marker=MARK[s], color=SCOL[s], lw=2.5, ms=6.8, label=lab, zorder=3)

    ax2.axhline(0, color=MUTED, lw=0.9, ls=":")
    ax2.text(0.0, 109, "全局铁律：同锚点渐进嵌套叠加（Clean → S1 → S2 → S3，同目标单元率 100%）",
             ha="left", va="center", fontsize=8.6, color="#1b7f79", weight="bold",
             bbox=dict(boxstyle="round,pad=0.28", fc="#e8f6f3", ec="#1b7f79", lw=0.85))

    ax2.set_xticks(xs, ["干净代码\n(锁定故障锚点)", "S1 轻度\n局部内聚退化", "S2 中度\n跨窗/跨模块耦合", "S3 重度\n契约与控制流交织"])
    ax2.set_xlim(-0.12, 3.34)
    ax2.set_ylim(-8.5, 118)
    ax2.set_ylabel("预期不可屏蔽认知负荷指数（设计示意，S3=100）")
    ax2.set_title("新版 S1–S3 设计：逐档跨越不可屏蔽的认知门槛", loc="left")
    ax2.legend(loc="upper left", bbox_to_anchor=(0.0, 0.91), fontsize=8.2)

    title(fig, "图 13  从“失真平台”到“单调梯度”：现行 S0–S2 曲线成因诊断与新版 S1–S3 渐进嵌套设计原理",
          "左图为现行基准实测的三大失真机制；右图为锁定同一故障锚点、仅递增“不可被窗口屏蔽因子”后的单调设计机制")
    fig.savefig(STATE["out"] / "fig12_s1_s3_redesign.png")
    plt.close(fig)


if __name__ == "__main__":
    for notitle in (False, True):
        STATE.update(out=FIG / "slide" if notitle else FIG, notitle=notitle)
        for fn in (fig1, fig2, fig3b, fig3, fig4, fig5, fig6, fig7, fig8, fig9, fig10, fig11, fig12):
            fn()
    print("figures ->", FIG)
