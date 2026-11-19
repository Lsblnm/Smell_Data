# smell_paper：透过代码坏味看底层逻辑（实证论文与汇报幻灯片）

围绕**职责分离度（内聚与信噪比）、数据–行为局部性（耦合与契约归属）、控制流复杂度（分支嵌套与可切片性）**三个底层逻辑维度，结合 2,424 份注入补丁结构与 9,696 条智能体四阶段执行轨迹重新完成的深度研究。

| 产物 | 说明 |
|---|---|
| [PAPER.pdf](PAPER.pdf) / [PAPER.md](PAPER.md) | 完整论文版（开篇直击三大底层逻辑成因、生产文件跨度单调实证与同题赛马回归、四阶段轨迹拆解、治理路线图与 `S1～S3` 单调基准规范） |
| [SLIDES.pptx](SLIDES.pptx) | 12 页简明汇报演示文稿（开篇“三问三答”一眼抓准结论、五段式清晰叙事、无术语堆砌） |
| `figures/` | 13 张论文插图（`figures/slide/` 为幻灯片无标题版本） |
| `structural.py` | 补丁底层结构特征（拓扑耦合、控制流分支增量、故障点纠缠）与四阶段轨迹拆解模块 |
| `accounting.py` | 多轮对话上下文重算来源精确拆解模块 |
| `data/results.json` | 论文与幻灯片全部统计量和置信区间的唯一数据源 |

一键复现（Python 3.12）：

```bash
python parse_traces.py   # 解析 9,696 条轨迹与 272,200 次工具调用
python analysis.py       # 提取底层结构指标并运行仓库聚类统计 -> data/results.json
python figures.py        # 生成全部论文插图与幻灯片插图
python build_paper.py    # 渲染 PAPER.html 与 PAPER.pdf
python build_slides.py   # 生成 SLIDES.pptx
```
