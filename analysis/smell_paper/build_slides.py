"""Build a concise, reader-friendly 12-slide presentation SLIDES.pptx with crystal-clear takeaways."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
FIG = HERE / "figures" / "slide"

INK = RGBColor(0x1F, 0x2A, 0x36)
MUTED = RGBColor(0x63, 0x70, 0x7E)
TEAL = RGBColor(0x1B, 0x7F, 0x79)
ORANGE = RGBColor(0xD9, 0x82, 0x2B)
PURPLE = RGBColor(0x5B, 0x4B, 0x9A)
RED = RGBColor(0xC0, 0x39, 0x2B)
LIGHT = RGBColor(0xF3, 0xF6, 0xF8)
SOFT_TEAL = RGBColor(0xE8, 0xF3, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "PingFang SC"
TOTAL = 12

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
W, H = prs.slide_width, prs.slide_height
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, s, size=15, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, after=5):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    lines = s if isinstance(s, list) else [s]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        segs = line if isinstance(line, list) else [(line, {})]
        for seg in segs:
            if isinstance(seg, str):
                seg = (seg, {})
            r = p.add_run()
            r.text = seg[0]
            f = r.font
            f.name = FONT
            f.size = Pt(seg[1].get("size", size))
            f.bold = seg[1].get("bold", bold)
            f.color.rgb = seg[1].get("color", color)
        p.space_after = Pt(segs[-1][1].get("after", after) if isinstance(segs[-1], tuple) else after)
    return tb


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
    s.shadow.inherit = False
    return s


def header(slide, title, kicker, num):
    rect(slide, 0, 0, W, Inches(0.11), TEAL)
    text(slide, Inches(0.5), Inches(0.24), Inches(11), Inches(0.32), kicker, size=11.5, color=TEAL, bold=True, after=0)
    text(slide, Inches(0.5), Inches(0.52), Inches(12.33), Inches(0.72), title, size=21.2, bold=True, after=0)
    text(slide, Inches(0.5), Inches(7.08), Inches(9), Inches(0.28),
         "代码坏味如何影响 AI 辅助开发 · 41 个仓库、7,223 组对比实验实证报告", size=9.5, color=MUTED, after=0)
    text(slide, Inches(11.68), Inches(7.08), Inches(1.15), Inches(0.32), f"{num} / {TOTAL}",
         size=9.5, color=MUTED, align=PP_ALIGN.RIGHT, after=0)


def bullets(slide, x, y, w, h, items, size=13.5, after=5):
    lines = []
    for it in items:
        if isinstance(it, tuple):
            lines.append([("■ ", {"color": TEAL, "size": size - 2.5}),
                          (it[0], {"bold": True, "size": size}),
                          (it[1], {"size": size, "after": after})])
        else:
            lines.append([("■ ", {"color": TEAL, "size": size - 2.5}),
                          (it, {"size": size, "after": after})])
    return text(slide, x, y, w, h, lines, size=size, after=after)


def fig_slide(num, kicker, title, figure, take, fig_h=3.82):
    s = prs.slides.add_slide(BLANK)
    header(s, title, kicker, num)
    pic = s.shapes.add_picture(str(FIG / figure), Inches(0.5), Inches(1.34), height=Inches(fig_h))
    if pic.width > Inches(12.33):
        ratio = Inches(12.33) / pic.width
        pic.width = Inches(12.33)
        pic.height = int(pic.height * ratio)
    pic.left = int((W - pic.width) / 2)
    top = pic.top + pic.height + Inches(0.14)
    box_h = Inches(6.95) - top
    rect(s, Inches(0.5), top, Inches(12.33), box_h, LIGHT)
    bullets(s, Inches(0.68), top + Inches(0.10), Inches(11.95), box_h - Inches(0.16), take, size=13.3, after=5)
    return s


# ==================== Slide 1: Clean Cover ====================
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, RGBColor(0x12, 0x2B, 0x33))
rect(s, Inches(0.78), Inches(1.95), Inches(0.12), Inches(2.45), TEAL)
text(s, Inches(1.12), Inches(1.88), Inches(11.3), Inches(0.92),
     "代码坏味如何影响 AI 辅助开发？", size=41, bold=True, color=WHITE)
text(s, Inches(1.12), Inches(2.86), Inches(11.3), Inches(1.1),
     "影响曲线真相、底层根因拆解与治理介入指南",
     size=22.5, color=RGBColor(0xCF, 0xE8, 0xE6))
text(s, Inches(1.12), Inches(4.52), Inches(11.3), Inches(1.35),
     ["实验规模：41 个开源项目 · 7 种编程语言 · 297 道真实缺陷 · 7,223 组同题对比实验",
      "评测对象：对比旗舰模型 GPT-5.6 与轻量模型 GLM-5.3、DeepSeek-V4.1 在干净代码和坏味代码上的表现",
      "完整论文报告：analysis/smell_paper/PAPER.pdf"],
     size=13.5, color=RGBColor(0xA9, 0xC4, 0xC8), after=7)

# ==================== Slide 2: 3 Plain-Language Key Takeaways ====================
s = prs.slides.add_slide(BLANK)
header(s, "先看结论：全篇最关键的三个发现（一页读懂核心主旨）", "开篇总览 · 核心结论", 2)

qa_cards = [
    ("问题 1\n坏味到底影响什么？", TEAL,
     "主要推高开发成本（+8% 至 +31%），强模型保住了通过率，轻量模型易“算力爆表”",
     "旗舰模型 GPT 靠多花 8% Token 稳住了修复通过率（仅波动 -1.2%）；但两款轻量模型平均多花约 30% Token、多走 13% 步数，且约 1/4 的任务出现单题成本翻倍。"),
    ("问题 2\n影响曲线长什么样？", ORANGE,
     "按 S0–S2 看走平只是分档假象；改按“改动文件数”和“函数内分支数”画图，开销单调上升",
     "原实验在轻度档（S0）就已把逻辑拆散到多个文件（透支了 70%～88% 的涨幅），后续往大类末尾塞几千行无关方法会被 AI 自动跳过。同题回归证实：跨文件数、控制流分支数、核心故障逻辑是否受牵连才是真正的决定因素。"),
    ("问题 3\n什么时候介入治理？", PURPLE,
     "别等文件上千行才按体积切分，在高频修改模块守住“防跨类拆散”与“160 行函数红线”",
     "一旦打破职责边界就已付出八成代价，事后把 6,000 行大类切半几乎不省钱；最有效的干预是让核心逻辑留在它的数据类里，并将单个函数控制在 160 行、4 层嵌套以内（保留小函数名帮 AI 定位深层根因）。"),
]

y_top = Inches(1.42)
card_h = Inches(1.68)
gap_y = Inches(0.20)
for idx, (q_txt, col, headline, detail) in enumerate(qa_cards):
    yy = y_top + idx * (card_h + gap_y)
    rect(s, Inches(0.5), yy, Inches(12.33), card_h, LIGHT)
    rect(s, Inches(0.5), yy, Inches(2.55), card_h, col)
    text(s, Inches(0.62), yy + Inches(0.12), Inches(2.31), card_h - Inches(0.24),
         q_txt.split("\n"), size=15.5, bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, after=4)
    text(s, Inches(3.26), yy + Inches(0.18), Inches(9.38), Inches(0.46),
         headline, size=15.2, bold=True, color=INK, after=2)
    text(s, Inches(3.26), yy + Inches(0.70), Inches(9.38), Inches(0.88),
         detail, size=12.4, color=MUTED, after=2)

# ==================== Slide 3: Global Impact (Fig 1) ====================
fig_slide(3, "第一部分：现象与账单",
          "全局账单：坏味带来 8%～31% 的额外成本，轻量模型代价是强模型的近 4 倍",
          "fig1_overview.png", [
              ("理解与交互成本全线上升：", "GPT 每题中位多花 2.5 万 Token（+7.8%）；GLM 与 DeepSeek 多花 9 万～13 万 Token（+30.9% / +29.5%），交互步数增加约 13%。"),
              ("强模型交付质量稳健：", "GPT 在轻度（S0）与重度（S2）下的通过率变化均为 -1.4 个百分点，说明强模型能靠多读几轮消化坏味；但轻量模型另有约 25% 的单题成本翻倍风险。"),
          ], fig_h=3.70)

# ==================== Slide 4: Apparent S0-S2 Curve Puzzle (Fig 2) ====================
fig_slide(4, "第二部分：解开影响曲线之谜",
          "表面困惑：按现行 S0→S1→S2 分档，为什么轻度坏味就占了七至九成涨幅？",
          "fig2_dose_curves.png", [
              ("刚有坏味即封顶：", "从干净代码到轻度（S0）就已占去总涨幅的 68%～88%；继续加重到 S2，依恋情结走平，上帝类甚至在 S2 回落，唯独长方法持续爬升。"),
              ("核心追问：", "为什么把坏味指标放大几倍却少见涨价？是因为严重度本身不重要，还是因为 S0–S2 的构造方式锁死了真正关键的变量？"),
          ], fig_h=3.75)

# ==================== Slide 5: Direct Empirical Proof Along Production Files (Fig 3B) ====================
fig_slide(5, "第二部分：解开影响曲线之谜（关键实证）",
          "换对横轴见真相：改按“改动生产文件数”重画曲线，三模型开销全线单调上升",
          "fig3b_driver_curves.png", [
              ("文件跨度是真实单调量（左、中）：", "现行 S0–S2 内改动文件数中位数完全锁死；改按真实改动文件数（1→2→3–5→≥6）展开后三模型全线单调爬升。依恋情结在 1 个文件内 GPT 零损耗（-0.4%），跨出第 2 个文件即跳至 +7.6%（GLM 跳至 +30.7%）。"),
              ("同题回归定论（右）：", "控制原题难度后，表面档位 S0–S2 的独立解释力归零（p > 0.38），改动生产文件数、新增控制流分支数、核心故障逻辑纠缠才是决定开销的三大硬指标。"),
          ], fig_h=3.68)

# ==================== Slide 6: Horizontal Sibling Shielding vs Vertical Branch Growth (Fig 3) ====================
fig_slide(6, "第二部分：解开影响曲线之谜（视野过滤机制）",
          "横向堆方法 vs 纵向塞分支：AI 自动跳过无关并列方法，却绕不开函数内分支",
          "fig3_topology_vs_complexity.png", [
              ("横向并列堆砌被窗口屏蔽（中）：", "上帝类在文件末尾多塞 4,800 行独立方法，但 AI 靠搜索定位加限长读取，GPT 三档实际读入量恒定（约 18.5k 字符）；超 5,000 行后 AI 放弃顺序翻页，导致 S2 比 S1 更省。"),
              ("纵向控制流分支必读（右）：", "长方法把逻辑塞进待修函数内部，AI 必须逐屏读完（多读字符翻 5 倍）；全样本按新增分支数分箱后三模型开销同样显著单调上升。"),
          ], fig_h=3.72)

# ==================== Slide 7: 4-Stage Trajectory Anatomy (Fig 4) ====================
fig_slide(7, "第三部分：深入执行轨迹查病根",
          "拆解 AI 干活过程：找文件一点不慢，真正贵在“进门难懂、改错行与多轮重算”",
          "fig4_four_stages.png", [
              ("找门不慢，进门后卡壳：", "首次找到并打开目标文件前的步数零差异；进门后厘清逻辑多花约 2 步，深层缩进与重复代码块使 GLM 改代码匹配报错率翻了 2.5 倍（4.4%→10.8%）。"),
              ("一次多读，轮轮买单：", "由于每轮工具调用都要重读完整历史对话，前期多吞进来的混杂代码会在后续十几轮里被反复计费，直接贡献了 50%～77% 的新增 Token。"),
          ], fig_h=3.72)

# ==================== Slide 8: Fault-Site Entanglement Watershed (Fig 7) ====================
fig_slide(8, "第三部分：深入执行轨迹查病根",
          "关键分水岭：旁边的辅助坏味无伤大雅，“待修改的核心逻辑脱离数据”才致命",
          "fig7_fault_entanglement.png", [
              ("周边坏味 vs 核心逻辑脱离数据：", "当待修复方法仍留在原数据类内时，GPT 几乎零损耗（+0.4%）；一旦故障方法自身被迁走，同一道原题内 GPT 开销立增 +8.7%，GLM 飙升至 +30.8%。"),
              ("为什么这么贵？", "核心逻辑迁入通用容器后，AI 不仅被迫跨双文件反复核对（同查率翻倍至 43%～75%），改代码时还极易误伤同一容器上的其他调用方契约，引发连续测试报错返工。"),
          ], fig_h=3.72)

# ==================== Slide 9: 160-Line Window Knee & Premature Convergence (Fig 8) ====================
fig_slide(9, "第三部分：深入执行轨迹查病根",
          "复杂度红线：函数超过约 160 行成本跳升 5 倍，抹掉小函数名易让 AI“漏修深层 Bug”",
          "fig8_complexity_knee_and_failure.png", [
              ("约 160 行的单屏感知拐点（左）：", "GPT 默认每次读取约 180 行；函数在 160 行以内仅增 +2.5%，跨过 160 行（嵌套达 5～8 层）被迫多段翻页后，额外成本跳升 5 倍至 +13.1%。"),
              ("失去路标诱发提前收工（右）：", "具名小函数原本是 AI 定位缺陷的路标；被压平进巨型分支后，失败案例反而比同题成功案例少跑 0.79 次测试、少花 14% Token——只修表面报错便草率交卷。"),
          ], fig_h=3.70)

# ==================== Slide 10: Governance Roadmap (Fig 11) ====================
s = prs.slides.add_slide(BLANK)
header(s, "工程治理指南：在边界打破前设防，聚焦高频修改模块守住三条红线", "第四部分：何时干预 · 怎么治理", 10)
s.shapes.add_picture(str(FIG / "fig11_governance.png"), Inches(0.5), Inches(1.40), height=Inches(3.52))
gov_rows = [
    ["治理维度", "何时触发干预", "正确的重构动作"],
    ["防职责混杂\n针对巨型类", "热点类混入 ≥3 个外部职责，或内聚度跌破 0.2", "按业务边界剥离异质职责；单纯按行数把大类切半几乎无效"],
    ["保数据就近\n针对跨类调用", "核心方法脱离持有数据的类，改功能总要开俩文件", "让核心方法回到状态宿主类，消除转发壳与共享容器误伤"],
    ["控函数跨度\n针对超长函数", "函数 >160 行或嵌套 >4 层（轻量模型收紧至 80～100 行）", "提炼语义清晰的具名小函数作路标，并强制跑完关联回归测试"],
]
tbl = s.shapes.add_table(4, 3, Inches(7.72), Inches(1.42), Inches(5.11), Inches(3.52)).table
for j, wd in enumerate([1.35, 1.88, 1.88]):
    tbl.columns[j].width = Inches(wd)
for i, row in enumerate(gov_rows):
    for j, v in enumerate(row):
        c = tbl.cell(i, j)
        c.text = v
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in c.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(10.6)
                r.font.name = FONT
                r.font.bold = (i == 0 or j == 0)
                r.font.color.rgb = WHITE if i == 0 else INK
        c.fill.solid()
        c.fill.fore_color.rgb = TEAL if i == 0 else (LIGHT if i % 2 else WHITE)

rect(s, Inches(0.5), Inches(5.22), Inches(12.33), Inches(1.70), SOFT_TEAL)
bullets(s, Inches(0.68), Inches(5.32), Inches(11.95), Inches(1.52), [
    ("防破界远优于事后减重：", "一旦跨文件破界就已产生七至九成损耗，代码评审应重点拦截高频模块“第一次混入异质职责”；无人问津的边缘老文件无需专门折腾。"),
    ("小需求与轻量模型最受益：", "剥离坏味相当于每次约 2.5 万 Token 的固定门槛，日常几行代码的小改动最吃亏；团队推广轻量高性价比模型前，必须先收紧上述三条门禁。"),
], size=13.2, after=5)

# ==================== Slide 11: S1-S3 Monotonic Design Principles (Fig 12) ====================
fig_slide(11, "第五部分：下一代 S1～S3 单调基准设计（原理）",
          "如何设计 S1～S3 走出单调曲线？锁定同一故障点，逐档递增“不可屏蔽”的因子",
          "fig12_s1_s3_redesign.png", [
              ("铁律一（同锚点渐进嵌套 Clean → S1 → S2 → S3）：", "现行三档独立选点使同方法率仅 27%～62%；新版固定同一待修方法逐档叠加演化（同题四档交错并发运行），彻底消除选点漂移与随机倒挂。"),
              ("铁律二（逐级跨越真实认知门槛）：", "解绑轻度档跨模块锁死，禁靠文件末尾堆孤立方法凑行数；按“S1 同模块/单屏内 → S2 跨模块双向耦合/超 160 行 → S3 多跳共享契约/抹除路标”递进。"),
          ], fig_h=3.68)

# ==================== Slide 12: S1-S3 Concrete Parameter Matrix ====================
s = prs.slides.add_slide(BLANK)
header(s, "S1～S3 具体分级规范：三类代码坏味与架构坏味的单调参数矩阵", "第五部分：下一代 S1～S3 单调基准设计（参数表）", 12)

spec_rows = [
    ["坏味与核心递增因子", "S1 轻度（局部感知层）", "S2 中度（跨界消歧层）", "S3 重度（契约与根因交织层）"],
    ["依恋情结\n跳数 × 读写 × 宿主契约",
     "同包单跳只读搬移（2 文件、1 模块）；外部属性 4–6 个，新宿主无共享契约冲突",
     "跨模块双端读写（3–4 文件、2 模块）；外部属性 7–10 个，含状态回写或双向回调",
     "跨 ≥3 模块、≥2 跳委托链（≥5 文件）；终点落在多业务共用的可变状态容器上"],
    ["上帝类\n共享字段 × 同名词 × 纠缠",
     "吸收同模块辅助类（500–1,000 行，内聚度 0.20–0.35）；与待修方法状态完全隔离",
     "跨 2 模块混入（1,200–2,200 行）；共享 ≥2 个可变字段，周边布置 3–5 处同名词诱饵",
     "跨 ≥3 模块融合（严控 2,200–3,800 行防弃读）；待修路径直接调用迁入前置逻辑"],
    ["长方法\n窗口跨度 × 嵌套 × 抹路标",
     "仅展开本类小函数；70–130 行（留在单屏内，修改点 <90 行），分支 12–22，嵌套 3–4 层",
     "跨文件分支内联；160–250 行（突破单屏截断，修改点 ≥140 行），分支 25–45，嵌套 5–6 层",
     "跨模块全流程压平并抹除具名子函数路标；260–450 行，分支 50–85，嵌套 7–8 层"],
    ["架构坏味扩展\n契约变更传播跳数",
     "双模块单向跨层直连：绕过接口直接依赖底层内部结构，需 2 个文件同步核对",
     "三模块闭环循环依赖（A→B→C→A）：单点修改触发环路契约与回调冲突",
     "散弹式契约分散 + ≥4 模块环网校验：同一规则散落 ≥5 个类，漏改即测试失败"],
]
tbl = s.shapes.add_table(5, 4, Inches(0.5), Inches(1.38), Inches(12.33), Inches(3.82)).table
for j, wd in enumerate([2.55, 3.16, 3.26, 3.36]):
    tbl.columns[j].width = Inches(wd)
for i, rh in enumerate([0.46, 0.84, 0.84, 0.84, 0.84]):
    tbl.rows[i].height = Inches(rh)
for i, row in enumerate(spec_rows):
    for j, v in enumerate(row):
        c = tbl.cell(i, j)
        c.text = v
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in c.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(10.3)
                r.font.name = FONT
                r.font.bold = (i == 0 or j == 0)
                r.font.color.rgb = WHITE if i == 0 else INK
        c.fill.solid()
        c.fill.fore_color.rgb = TEAL if i == 0 else (LIGHT if i % 2 else WHITE)

rect(s, Inches(0.5), Inches(5.40), Inches(12.33), Inches(1.52), SOFT_TEAL)
bullets(s, Inches(0.68), Inches(5.50), Inches(11.95), Inches(1.36), [
    ("关键防倒挂设计（上帝类主动限高 <3,800 行）：", "实测超过 5,000 行会促使 AI 放弃顺序翻页、改用关键词跳跃，导致 S2 成本反低于 S1；控制总体积并强制待修路径状态纠缠，才能确保 Clean < S1 < S2 < S3 严格单调。"),
    ("评测覆盖建议：", "在按此规范构造单调梯度的同时，补齐两款轻量模型与各档位的容器测试判定，即可同步绘出“成本单调上升 + 通过率单调衰减”的双重响应曲线。"),
], size=12.4, after=5)

prs.save(HERE / "SLIDES.pptx")
print("wrote", HERE / "SLIDES.pptx", len(prs.slides), "slides")
