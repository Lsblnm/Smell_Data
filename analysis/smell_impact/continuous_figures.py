"""Show all observed x values and a separate, magnified view of the empirical estimates."""

from io import BytesIO
import json
import re

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen.canvas import Canvas

from dimensions import LABEL
from figures import INK, MUTED, NAMES, RULE, configure, ratio_axis, write
from measure import LEVELS, MODELS, OUT, TRACES
from static_metrics import METRICS, RAD, NUMBERED


PALETTE = {"gpt": "#126c70", "glm": "#b45721", "deepseek": "#60559b"}
MARKS = {"gpt": "o", "glm": "s", "deepseek": "^"}
MODELTEXT = {"gpt": "GPT", "glm": "GLM", "deepseek": "DeepSeek"}
OUTCOMES = {"tokens": "总 token", "seconds": "墙钟耗时", "success": "修复通过率"}
PRIMARY = [("FE", "atfd"), ("GC", "loc"), ("LM", "loc")]


def label_x(smell, key):
    if key == "loc":
        return "目标类 LOC（行）" if smell == "GC" else "目标方法 LOC（行）"
    return LABEL[key]


def scatter_and_means(fig, slot, source, bins, smell, key, outcome, heading):
    top, lower = slot.subgridspec(2, 1, height_ratios=[1.0, 1.05], hspace=0.16)
    raw = fig.add_subplot(top)
    trend = fig.add_subplot(lower, sharex=raw)
    d = source[source.smell.eq(smell)].dropna(subset=[key, outcome])
    binary = outcome == "success"
    if binary:
        count = d.groupby([key, outcome]).size().reset_index(name="count")
        raw.scatter(
            count[key],
            count[outcome],
            s=5 + 3.2 * np.sqrt(count["count"]),
            color=PALETTE["gpt"],
            alpha=0.42,
            lw=0,
        )
        raw.set_yticks([-1, 0, 1], ["转失败", "相同", "转通过"], fontsize=8)
        raw.set_ylim(-1.42, 1.42)
    else:
        for m in MODELS:
            a = d[d.model == m]
            raw.scatter(
                a[key], np.exp(a[outcome]), s=5.1, alpha=0.21, lw=0, color=PALETTE[m], rasterized=True
            )
        vals = np.exp(d[outcome])
        ratio_axis(raw, vals.min() * 0.89, vals.max() * 1.13, max_ticks=5)
        raw.axhline(1, color="#667a83", lw=0.8)
    raw.tick_params(axis="x", labelbottom=False, length=0)
    raw.tick_params(axis="y", labelsize=8, length=2)
    raw.grid(axis="y", color=RULE, lw=0.45)
    raw.set_axisbelow(True)
    raw.set_title(heading, fontsize=13, pad=7, color=INK, weight="bold")
    model_list = ["gpt"] if binary else MODELS
    for m in model_list:
        series = bins[smell, m, key, outcome]
        x = np.array([r["x"] for r in series])
        y = np.array([r["estimate"] for r in series])
        lo = np.array([r["lo"] for r in series])
        hi = np.array([r["hi"] for r in series])
        if binary:
            trend.vlines(x, lo, hi, color=PALETTE[m], lw=1.25)
            trend.scatter(x, y, marker=MARKS[m], s=22, color=PALETTE[m], zorder=4)
        else:
            trend.fill_between(x, lo, hi, color=PALETTE[m], alpha=0.10, linewidth=0)
            trend.plot(x, y, color=PALETTE[m], lw=1.55, marker=MARKS[m], ms=3.7)
    trend.axhline(0, color="#586e77", ls="--", lw=0.8)
    trend.grid(axis="y", color=RULE, lw=0.48)
    trend.set_axisbelow(True)
    trend.tick_params(labelsize=8, length=2)
    trend.set_xlabel(label_x(smell, key), fontsize=10, labelpad=4, color=INK)
    trend.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
    trend.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{v:+.0f}" if binary else ("0%" if v == 0 else f"{v:+.0f}%"))
    )
    raw.margins(x=0.035)
    if key in (
        "loc",
        "wmc",
        "cc",
        "depth",
        "atfd",
        "fdp",
        "rad_files",
        "rad_modules",
        "target_file_delta",
    ):
        trend.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        trend.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    else:
        trend.xaxis.set_major_locator(MaxNLocator(nbins=5))
    if key == "atfd":
        trend.set_xticks([5, 7, 9, 11, 13])
    if key == "loc":
        trend.set_xticks([1000, 2500, 4000, 5500, 7000] if smell == "GC" else [60, 150, 250, 350, 450])
    return raw, trend


def page(source, bins, items, outcome, title, subtitle, foot):
    rows = (len(items) + 2) // 3
    fig = plt.figure(figsize=(13.6, 6.7 if rows == 1 else 10.4))
    fig.text(0.073, 0.966, title, fontsize=21, weight="bold", va="top", color=INK)
    fig.text(0.073, 0.90 if rows == 1 else 0.923, subtitle, fontsize=10, va="top", color=MUTED)
    models = ["gpt"] if outcome == "success" else MODELS
    handles = [
        Line2D([0], [0], marker=MARKS[m], color=PALETTE[m], lw=1.5, label=MODELTEXT[m], ms=5)
        for m in models
    ]
    fig.legend(
        handles=handles,
        loc="upper right",
        bbox_to_anchor=(0.985, 0.968),
        frameon=False,
        ncol=len(models),
        columnspacing=0.9,
        handlelength=1.5,
        fontsize=9,
    )
    grid = fig.add_gridspec(
        rows,
        3,
        left=0.076,
        right=0.974,
        top=0.78 if rows == 1 else 0.847,
        bottom=0.158 if rows == 1 else 0.095,
        wspace=0.27,
        hspace=0.54,
    )
    axes = []
    for i, (sm, metric) in enumerate(items):
        title_cell = NAMES[sm] if len({s for s, _ in items}) > 1 else label_x(sm, metric)
        raw, trend = scatter_and_means(
            fig, grid[i // 3, i % 3], source, bins, sm, metric, outcome, title_cell
        )
        axes.append((raw, trend))
        if i % 3 == 0:
            raw.set_ylabel("单题判定" if outcome == "success" else "逐题比值", fontsize=9)
            trend.set_ylabel("通过率差（百分点）" if outcome == "success" else "分段估计", fontsize=9)
    if rows == 1:
        trend_lo = min(t.get_ylim()[0] for _, t in axes)
        trend_hi = max(t.get_ylim()[1] for _, t in axes)
        raw_lo = min(r.get_ylim()[0] for r, _ in axes)
        raw_hi = max(r.get_ylim()[1] for r, _ in axes)
        for raw, trend in axes:
            trend.set_ylim(trend_lo, trend_hi)
            if outcome != "success":
                ratio_axis(raw, raw_lo, raw_hi, max_ticks=5)
    fig.text(0.076, 0.034 if rows == 1 else 0.025, foot, fontsize=8.5, color=MUTED)
    return fig


def content_cases(frame):
    rows = []
    specs = [
        (
            "apache__lucene-12626",
            "Lucene · 回滚元数据",
            r"void replace\(SegmentInfos other\)",
            r"^\s*lastGeneration\s*=",
        ),
        (
            "preactjs__preact-4316",
            "Preact · DOM 焦点事件",
            r"export function setProperty\(",
            r"if \(name\.toLowerCase\(\) in dom\)",
        ),
    ]
    for task, label, entry_regex, anchor_regex in specs:
        versions = frame[
            (frame.model == "gpt") & (frame.smell == "LM") & (frame.task == task)
        ].set_index("level")
        for level in ["None", *LEVELS]:
            ctrl = level == "None"
            r = versions.loc["S0" if ctrl else level]
            prefix = "b_" if ctrl else "v_"
            group = "None-LM" if ctrl else "LM-" + level
            num = int(r[prefix + "target_windows"])
            path = TRACES / "gpt" / group / task / "trajectory.jsonl"
            header, anchor = None, None
            read_lines = []
            for n, line in enumerate(path.open("rb"), 1):
                evt = json.loads(line)
                p = evt.get("part", {})
                state = p.get("state", {})
                if p.get("tool") != "read" or state.get("status") != "completed":
                    continue
                filename = state.get("input", {}).get("filePath", "")
                if not (filename == r.target or filename.endswith("/" + r.target)):
                    continue
                read_lines.append(n)
                content = state["output"].partition("<content>")[2].partition("</content>")[0]
                for match in NUMBERED.finditer(content):
                    if re.search(entry_regex, match[2]):
                        header = int(match[1])
                    if re.search(anchor_regex, match[2]):
                        anchor = int(match[1])
                if len(read_lines) == num:
                    break
            assert (
                header is not None and anchor is not None and anchor > header and len(read_lines) == num
            )
            rows.append(
                dict(
                    task=task,
                    label=label,
                    level=level,
                    entry=header,
                    anchor=anchor,
                    distance=anchor - header,
                    reads=num,
                    trace_lines=read_lines,
                    tokens=int(r[prefix + "tokens"]),
                    ratio=float(r[prefix + "tokens"] / r.b_tokens),
                    loc=None if ctrl else int(r["loc"]),
                    cc=None if ctrl else int(r.cc),
                    depth=None if ctrl else int(r.depth),
                )
            )
    return rows


def case_plot(rows):
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.4))
    fig.subplots_adjust(left=0.085, right=0.978, top=0.73, bottom=0.22, wspace=0.2)
    fig.text(
        0.077, 0.959, "修复位置离方法入口多远，会怎样改变阅读？", fontsize=19, weight="bold", va="top"
    )
    fig.text(
        0.077,
        0.855,
        "每点是 GPT 修复同一原题的一次运行。横坐标由源码行号相减，可在原轨迹中逐行核对。",
        fontsize=10,
        color=MUTED,
    )
    for task, col, marker in [
        ("apache__lucene-12626", "#166e70", "o"),
        ("preactjs__preact-4316", "#a35628", "s"),
    ]:
        a = sorted((r for r in rows if r["task"] == task), key=lambda r: r["distance"])
        for ax, key in zip(axes, ["reads", "ratio"]):
            scale = 1 if key == "reads" else 100
            base = 0 if key == "reads" else 1
            x = [r["distance"] for r in a]
            y = [(r[key] - base) * scale for r in a]
            ax.plot(x, y, c=col, marker=marker, lw=1.55, ms=5, label=a[0]["label"])
    for ax in axes:
        ax.tick_params(labelsize=9)
        ax.grid(axis="y", color=RULE, lw=0.55)
        ax.set_xlabel("方法入口至目标语句的物理行距", labelpad=6)
        ax.set_xlim(-8, 310)
    axes[0].set_title("首次修改前，目标文件读了几次")
    axes[0].set_ylabel("结构化读取次数")
    axes[0].set_yticks([1, 2, 3, 4, 5])
    axes[1].set_title("整次修复的 token 变化")
    axes[1].set_ylabel("相对该任务无注入对照")
    axes[1].axhline(0, lw=0.8, ls="--", c=MUTED)
    axes[1].yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.text(
        0.085,
        0.052,
        "Lucene 题面已给出修复代码。左图统计首次编辑前的目标文件读取，右图还包含测试与后续修订。",
        color=MUTED,
        fontsize=9,
    )
    write(fig, "localization-scatter.png")


def render_continuous(frame, f, graded, bins):
    configure()
    plt.rcParams["pdf.fonttype"] = 42
    all_pages = []
    for outcome in OUTCOMES:
        binary = outcome == "success"
        source = graded if binary else f
        title = OUTCOMES[outcome] + (" " if outcome == "tokens" else "") + "随代码指标怎样变化？"
        subtitle = (
            "上排给出每题的判定变化，重合点以大小表示数量。下排显示双边均判定原题的通过率差与 95% 区间。"
            if binary
            else "上排是每个原题在同一模型下的注入 / 对照比值，保留全部散点。下排放大各模型随指标变化的局部均值与 95% 区间。"
        )
        foot = (
            "横轴使用注入说明记录的数值。分段内按原题等权，区间按仓库重抽样。上排和下排的纵轴刻度不同。"
        )
        fig = page(source, bins, PRIMARY, outcome, title, subtitle, foot)
        write(
            fig,
            {
                "tokens": "token-scatter.png",
                "seconds": "time-scatter.png",
                "success": "success-by-metric.png",
            }[outcome],
        )
        if outcome == "tokens":
            factor_fig = page(
                source,
                bins,
                [("LM", "loc"), ("LM", "cc"), ("LM", "rad_files")],
                outcome,
                "长方法的长度、复杂度、文件分散度与总 token",
                subtitle,
                foot,
            )
            write(factor_fig, "long-method-factors.png")
        for sm, fields in METRICS.items():
            all_pages.append(
                (
                    source,
                    [(sm, key) for key in [*fields, *RAD]],
                    outcome,
                    NAMES[sm] + " 与" + OUTCOMES[outcome],
                    subtitle,
                    "指标来自注入说明。分段至少含 15 道不同原题及 5 个仓库。上下排分别显示原始观测与局部估计。",
                )
            )
        all_pages.append(
            (
                source,
                [(s, "target_file_delta") for s in METRICS],
                outcome,
                "目标文件实际增减的行数与" + OUTCOMES[outcome],
                subtitle,
                "横轴取目标文件统一差异补丁各 hunk 的新增行数减去删除行数，含空行、注释。",
            )
        )
    out = OUT / "output/pdf/metric-atlas.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(str(out), invariant=1, pageCompression=1)
    canvas.setTitle("代码坏味的连续指标与任务结果 | Smell Data")
    canvas.setAuthor("Smell Data")
    # Use a TrueType CJK face when embedding CIDFontType2 in PDF viewers.
    original_fonts = plt.rcParams["font.family"]
    installed = {face.name for face in font_manager.fontManager.ttflist}
    for face in ("Arial Unicode MS", "STHeiti", "Microsoft YaHei", "WenQuanYi Zen Hei"):
        if face in installed:
            plt.rcParams["font.family"] = ["DejaVu Sans", face]
            break
    for index, (source, items, outcome, title, subtitle, foot) in enumerate(all_pages, 1):
        fig = page(
            source, bins, items, outcome, title, subtitle, foot + f"    {index} / {len(all_pages)}"
        )
        buf = BytesIO()
        fig.savefig(buf, format="pdf", dpi=150, metadata={"CreationDate": None, "ModDate": None})
        canvas.setPageSize(tuple(fig.get_size_inches() * 72))
        form = pagexobj(PdfReader(fdata=buf.getvalue()).pages[0])
        canvas.bookmarkPage(str(index))
        canvas.addOutlineEntry(title, str(index))
        canvas.doForm(makerl(canvas, form))
        canvas.showPage()
        plt.close(fig)
    canvas.save()
    plt.rcParams["font.family"] = original_fonts
    cases = content_cases(frame)
    case_plot(cases)
    return cases
