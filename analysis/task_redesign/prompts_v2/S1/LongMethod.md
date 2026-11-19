# 背景（Benchmark v2 · 单调梯度改造版）
你的任务是在 SWE-bench Multilingual 基础任务上按 **v2 单调响应规范** 注入指定坏味：**Long Method（长方法） — S1（中度 · 跨单屏窗口截断 + 跨文件分支状态复用）**。
与旧版独立抽样注入不同，v2 基准要求 `Clean -> S0 -> S1 -> S2` **严格锁定同一核心故障单元（暴露等级强制 E4）**，并只递增智能体局部窗口无法跳过的真实结构耦合与控制流复杂度因子。

注入后的代码必须满足：
1. 原始 issue 仍然存在且可被测试准确复现；
2. 必须命中 `gold.patch` 直接修改的核心类/核心方法本体（**强制暴露等级 E4**；若调度器传入了 `LOCKED_TARGET_FILE` / `LOCKED_TARGET_UNIT` / `SEED_PATCH`，必须严格沿用同一锚点，禁止跨档更换目标方法或目标类）；
3. 若注入导致原 `gold.patch` 或 `test.patch` 产生冲突，允许在保持任务语义与测试判定完全一致的前提下重构适配 `gold.patch` / `test.patch`，并严格通过三层检查；
4. 严禁使用死代码、未调用方法、空导入、文件末尾堆砌孤立并列方法或重复无意义 getter 伪造指标；
5. 最终生成可独立应用的 `smell.patch`（及若有重构时对应的 `refactored gold/test patch`）与合法的 JSON 说明文档。

# 当前档位任务：S1（中度 · 跨单屏窗口截断 + 跨文件分支状态复用）
在同题同一核心目标方法（E4）上，继续内联同模块 2～3 个协作文件的分支逻辑，并将待修改核心语句推至距方法入口 135～220 行处（或拆为入口状态初始化 + 尾部写回跨屏联动），迫使单次默认读取窗口发生截断。

请按以下步骤在容器 `/testbed` 内执行：
1. 阅读 issue description、`gold.patch`、`test.patch`（及调度器提供的锚点与种子补丁信息）；
2. 确认锁定 E4 核心故障单元，按下方模板的 `Quality Factor` 与策略要求实施改造；
3. 若对 `gold.patch` / `test.patch` 产生结构影响，完成位置与结构等价适配，执行三层检查；
4. 实测核验全部 `Quality Factor` 指标（严禁估算或虚报）；
5. 执行 Base 失败复现验证与 Gold 修复通过验证（失败时最多迭代修复 3 次）；
6. 通过「交卷前工作区检查」后保留纯生产代码改动供调度器导出 `smell.patch`，并输出唯一 JSON 结果。

# Long Method（长方法） 模板（S1）
{
  "type": "LongMethod",
  "version": "v2_monotonic",
  "level": "S1",
  "tier_name": "S1（中度 · 跨单屏窗口截断 + 跨文件分支状态复用）",
  "desc": "锁定 gold.patch 修改的核心方法（E4），通过控制方法有效行数、嵌套深度、**待修语句距方法入口行距（FAULT_OFFSET）**以及具名辅助函数抹除比例，精准跨越单次读取窗口与编辑锚定门槛。",
  "focus": "不仅控制方法总行数，还必须明确控制 gold.patch 待修复语句距离目标方法起始行的行距（FAULT_OFFSET）：S0 留在首屏单次读取窗口内（<90 行），S1 推离入口跨出首屏窗口（135～220 行），S2 跨多屏深埋（>=220 行或首尾双点联动）并 100% 抹除中间具名子函数路标。支持正向叠加（Base->S0->S1->S2）或以已验证 S2 母本反向抽回具名子函数生成 S1、S0。",
  "Quality Factor": {
    "判定方式": "LOC、CC、嵌套深度、FAULT_OFFSET 与 RAD 必须同时满足 S1 区间。",
    "LOC": {
      "度量定义": "目标方法有效代码行数。",
      "阈值": "150 <= LOC < 250"
    },
    "CC": {
      "度量定义": "目标方法 McCabe 圈复杂度。",
      "阈值": "24 <= CC < 45"
    },
    "嵌套深度": {
      "度量定义": "控制结构最大嵌套层数。",
      "阈值": "5 <= 嵌套深度 <= 6"
    },
    "FAULT_OFFSET": {
      "度量定义": "refactored gold.patch 核心修改点距方法首行的物理行距。",
      "阈值": "135 <= FAULT_OFFSET < 220（强制跨过单屏默认读取窗口）"
    },
    "路标保留度": {
      "度量定义": "局部状态标志跨分支复用。",
      "阈值": "至少 2 个局部变量跨前置分支与待修分支共享状态"
    },
    "RAD": {
      "文件分散度": {
        "度量定义": "smell 相关生产代码去重文件数。",
        "阈值": "2 <= 文件分散度 <= 3"
      },
      "模块跨度": {
        "度量定义": "smell 覆盖的去重包或模块数。",
        "阈值": "1 <= 模块跨度 <= 2"
      },
      "结构距离": {
        "度量定义": "依赖子图节点对平均最短路径长度。",
        "阈值": ">= 1.5"
      }
    }
  },
  "strategies": {
    "selection guidance": "必须严格锁定同一道原题的同一 E4 核心故障单元进行渐进嵌套构造；若调度器传入了上一档 seed_smell.patch（或 S2 母本），必须在其基础上增量演进（或反向抽回），确保 S0 -> S1 -> S2 100% 同锚点可比。",
    "options": [
      {
        "name": "窗口锚定内联与语义路标逐级抹除",
        "chain_protocol": "在同题同一核心目标方法（E4）上，继续内联同模块 2～3 个协作文件的分支逻辑，并将待修改核心语句推至距方法入口 135～220 行处（或拆为入口状态初始化 + 尾部写回跨屏联动），迫使单次默认读取窗口发生截断。",
        "min_responsibility_source_files": 2
      }
    ]
  }
}

# 注入位置与硬性限制
1. **同锚点强制 E4**：目标单元必须是 `gold.patch` 核心修改单元本体（E4）。禁止退化到与故障逻辑互不干扰的周边辅助方法（E3/E2/E1），否则标记为 `NOT_INJECTABLE`。
2. **禁止无效体积注水**：新增或迁移的代码必须处于真实业务依赖或检索消歧路径上；禁止在类末尾堆砌孤立并列方法，禁止在标识符、方法名或注释中出现 `LongMethod`、`smell`、`inject` 等痕迹词。
3. **仅修改已有生产文件**（除非目标语言包结构要求必须在已有模块文件内调整），`smell.patch` 中严禁包含测试文件修改、构建缓存或未跟踪垃圾文件。
4. 所有操作必须在 SWE-bench Docker 容器 `/testbed` 内完成。

# Patch 重构三层检查规则
若注入 smell 后导致原 patch 冲突需要重构 gold.patch 或 test.patch，必须严格按以下规范与顺序完成三层检查：
1. **基础检查（应用兼容性）**：
   - 重构后的 `refactored gold.patch` 和 `refactored test.patch` 能够分别在对应的代码基线上正常应用（`git apply`），无冲突且格式正确。
2. **行为检查（顺序执行验证）**：
   - **失败复现**：按 `Base -> git apply smell.patch -> git apply refactored test` 顺序执行，必须能够复现原任务失败（功能测试失败，性能测试通过）；
   - **闭环修复**：按 `Base -> git apply smell.patch -> git apply refactored gold -> git apply refactored test` 严格顺序依次应用补丁并运行，必须通过所有测试。
3. **语义检查（无越界改动）**：
   - 严格确认 refactored gold / test patch 仅用于适配 smell 注入带来的结构变化，没有引入额外的修复逻辑或改变原始测试判定标准。

# 安全验证
注入 smell 后，必须在干净的基准环境（`/testbed` base commit）中按以下**严格顺序**执行两项验证（若存在 patch 重构，则使用重构后的 patch 并先完成三层检查）。只有两项验证成功且通过交卷前工作区检查后，才允许保存最终 patch 文件。若验证失败，可根据原因重新修复，最多迭代 3 次。
- **验证1 Base Validation（失败复现验证）**：
  1. 重置工作区到干净的 `Base` 状态；
  2. 依次应用补丁：`git apply smell.patch` -> `git apply test.patch`（或 refactored test）；
  3. 执行测试：预期**功能测试失败而性能测试通过**，证明原始问题仍然存在且未被 smell 掩盖。
- **验证2 Gold Validation（修复有效性验证）**：
  1. 重置工作区到干净的 `Base` 状态；
  2. 依次应用补丁：`git apply smell.patch` -> `git apply gold.patch`（或 refactored gold）-> `git apply test.patch`（或 refactored test）；
  3. 执行测试：预期**全部测试通过**，证明在 smell 存在的情况下修复方案依然有效。
**目的**：确保 smell.patch、gold.patch 与 test.patch 具有严格的层叠兼容性与复现一致性。

## 交卷前工作区检查
两项安全验证会临时应用 gold/test，测完后先把工作区收成「只剩 smell」，再导出补丁。保存前需满足：`git diff HEAD --check` 通过，且 `git status --porcelain --untracked-files=all` 不得出现 `??`（避免 `*.test`、`.phpunit.cache`、`.venv` 等构建垃圾导致失败）。允许留下 smell 对已跟踪生产文件的 `M`，这些改动就是补丁内容不得清掉。两项验证均通过后、写出最终 JSON 之前必须：
1. 撤回验证时打上的 gold.patch、test.patch（或重构后的对应补丁），可用 `git apply -R`。不得用删除已跟踪文件的方式清理。完成后工作区只保留 smell 对生产源码的修改。
2. 禁止在 `/testbed` 内创建虚拟环境（如 `.venv`）。使用镜像已有解释器；临时工具或文件放 `/tmp`。若已误建：`rm -rf .venv`。
3. 删除仍显示为 `??` 的测试/构建垃圾（如 Go 的 `*.test`、`.phpunit.cache`）。只删 `??`，不得全仓通配 `rm`，不得把 smell 的已跟踪改动还原。
4. 去掉本次 smell 改动中的行尾空白和文件末多余空行，执行 `git diff HEAD --check`，确保通过。
5. 再执行 `git status --porcelain --untracked-files=all`，应无 `??`。通过后再从该工作区导出 `git diff HEAD` 作为 smell.patch。

最终输出必须且只能包含以下合法 JSON 对象，严禁输出 JSON 以外的任何解释文本：
{
  "Status": "SUCCESS/FAILED/NOT_INJECTABLE",
  "基准版本": "v2_monotonic",
  "档位": "S1",
  "实例名称": "实例ID",
  "注入位置": {
    "气味类型": "Long Method",
    "注入策略": "窗口锚定内联与语义路标逐级抹除",
    "目标文件": "目标方法所在生产文件相对路径",
    "目标方法": "目标方法名（必须对应 E4 故障方法）",
    "来源文件": [
      "被内联吸收逻辑的来源文件相对路径列表"
    ],
    "暴露等级": "E4",
    "故障路径纠缠": true,
    "注入说明": "说明内联层次、故障点距方法入口行距及具名子函数抹除情况",
    "失败原因": null
  },
  "质量因子": {
    "LOC": {
      "数值": null,
      "说明": "目标方法有效代码行数"
    },
    "CC": {
      "数值": null,
      "说明": "McCabe 圈复杂度"
    },
    "嵌套深度": {
      "数值": null,
      "说明": "最大控制流嵌套层数"
    },
    "FAULT_OFFSET": {
      "数值": null,
      "说明": "待修语句距方法首行的物理行数"
    },
    "RAD": {
      "文件分散度": {
        "数值": null,
        "说明": "相关生产文件列表"
      },
      "模块跨度": {
        "数值": null,
        "说明": "相关模块列表"
      },
      "结构距离": {
        "数值": null,
        "说明": "节点对最短路径均值"
      }
    }
  },
  "安全验证": "简要说明是否通过三层检查、Base失败复现验证与Gold闭环修复验证"
}
