# 背景（Benchmark v2 · 单调梯度改造版）
你的任务是在 SWE-bench Multilingual 基础任务上按 **v2 单调响应规范** 注入指定坏味：**Cyclic Dependency（模块级架构坏味：循环依赖与契约传播） — S1（中度 · 三模块闭环循环依赖 M1 -> M2 -> M3 -> M1）**。
与旧版独立抽样注入不同，v2 基准要求 `Clean -> S0 -> S1 -> S2` **严格锁定同一核心故障单元（暴露等级强制 E4）**，并只递增智能体局部窗口无法跳过的真实结构耦合与控制流复杂度因子。

注入后的代码必须满足：
1. 原始 issue 仍然存在且可被测试准确复现；
2. 必须命中 `gold.patch` 直接修改的核心类/核心方法本体（**强制暴露等级 E4**；若调度器传入了 `LOCKED_TARGET_FILE` / `LOCKED_TARGET_UNIT` / `SEED_PATCH`，必须严格沿用同一锚点，禁止跨档更换目标方法或目标类）；
3. 若注入导致原 `gold.patch` 或 `test.patch` 产生冲突，允许在保持任务语义与测试判定完全一致的前提下重构适配 `gold.patch` / `test.patch`，并严格通过三层检查；
4. 严禁使用死代码、未调用方法、空导入、文件末尾堆砌孤立并列方法或重复无意义 getter 伪造指标；
5. 最终生成可独立应用的 `smell.patch`（及若有重构时对应的 `refactored gold/test patch`）与合法的 JSON 说明文档。

# 当前档位任务：S1（中度 · 三模块闭环循环依赖 M1 -> M2 -> M3 -> M1）
在同题 S0 锚点基础上，纳入第 3 个关联业务模块 M3，构造真实的三模块有向闭环依赖（M1 -> M2 -> M3 -> M1），使状态初始化、参数传递或结果校验跨三方闭环流转。

请按以下步骤在容器 `/testbed` 内执行：
1. 阅读 issue description、`gold.patch`、`test.patch`（及调度器提供的锚点与种子补丁信息）；
2. 确认锁定 E4 核心故障单元，按下方模板的 `Quality Factor` 与策略要求实施改造；
3. 若对 `gold.patch` / `test.patch` 产生结构影响，完成位置与结构等价适配，执行三层检查；
4. 实测核验全部 `Quality Factor` 指标（严禁估算或虚报）；
5. 执行 Base 失败复现验证与 Gold 修复通过验证（失败时最多迭代修复 3 次）；
6. 通过「交卷前工作区检查」后保留纯生产代码改动供调度器导出 `smell.patch`，并输出唯一 JSON 结果。

# Cyclic Dependency（模块级架构坏味：循环依赖与契约传播） 模板（S1）
{
  "type": "CyclicDependency",
  "version": "v2_monotonic",
  "level": "S1",
  "tier_name": "S1（中度 · 三模块闭环循环依赖 M1 -> M2 -> M3 -> M1）",
  "desc": "打破模块间原有的单向分层边界，围绕 gold.patch 所在核心模块（E4）逐级建立“双模块跨层直连（S0） -> 三模块强连通循环依赖（S1） -> 四模块环网耦合与散弹式契约交叉校验（S2）”。",
  "focus": "面向模块级架构坏味评测：核心递增因子是**契约变更的跨模块传播跳数（Change Propagation Hops）与强连通分量规模（SCC）**，而非单纯增加 import 语句。循环依赖必须真实参与运行时状态传递、类型构造或回调校验，严禁使用死导入或未调用桩代码伪造环路。",
  "Quality Factor": {
    "判定方式": "三个模块必须构成单一强连通分量（SCC == 3），且环上每条跨模块边均在目标测试执行路径中被实际触发。",
    "SCC_MODULES": {
      "度量定义": "构成强连通有向环的去重模块数。",
      "阈值": "SCC_MODULES == 3"
    },
    "CYCLE_EDGES": {
      "度量定义": "环路上真实执行的跨模块调用/状态传递边数。",
      "阈值": "4 <= CYCLE_EDGES <= 6"
    },
    "CHANGE_HOPS": {
      "度量定义": "契约变更跨模块核对或联动修改跳数。",
      "阈值": "CHANGE_HOPS == 3"
    },
    "RAD": {
      "文件分散度": {
        "度量定义": "环路耦合涉及的去重生产文件数。",
        "阈值": "3 <= 文件分散度 <= 5"
      },
      "模块跨度": {
        "度量定义": "覆盖的去重包或模块数。",
        "阈值": "模块跨度 == 3"
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
        "name": "跨模块双向环路耦合与散弹式契约校验",
        "chain_protocol": "在同题 S0 锚点基础上，纳入第 3 个关联业务模块 M3，构造真实的三模块有向闭环依赖（M1 -> M2 -> M3 -> M1），使状态初始化、参数传递或结果校验跨三方闭环流转。",
        "min_responsibility_source_files": 3
      }
    ]
  }
}

# 注入位置与硬性限制
1. **同锚点强制 E4**：目标单元必须是 `gold.patch` 核心修改单元本体（E4）。禁止退化到与故障逻辑互不干扰的周边辅助方法（E3/E2/E1），否则标记为 `NOT_INJECTABLE`。
2. **禁止无效体积注水**：新增或迁移的代码必须处于真实业务依赖或检索消歧路径上；禁止在类末尾堆砌孤立并列方法，禁止在标识符、方法名或注释中出现 `CyclicDependency`、`smell`、`inject` 等痕迹词。
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
    "气味类型": "Cyclic Dependency",
    "注入策略": "跨模块双向环路耦合与散弹式契约校验",
    "目标文件": "核心入口模块生产文件相对路径",
    "核心单元": "核心类或方法名（E4）",
    "环路模块序列": [
      "模块1 -> 模块2 -> ... -> 模块1"
    ],
    "来源文件": [
      "参与环路耦合的所有生产文件相对路径"
    ],
    "暴露等级": "E4",
    "故障路径纠缠": true,
    "注入说明": "说明跨模块有向环构成方式、运行时触发路径及契约交叉校验点",
    "失败原因": null
  },
  "质量因子": {
    "SCC_MODULES": {
      "数值": null,
      "说明": "强连通环路包含的模块列表"
    },
    "CYCLE_EDGES": {
      "数值": null,
      "说明": "跨模块运行时依赖边列表"
    },
    "CHANGE_HOPS": {
      "数值": null,
      "说明": "契约传播涉及的文件跳数说明"
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
