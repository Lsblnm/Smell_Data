# 背景
你的任务是在 SWE-bench Multilingual 基础任务上注入指定 Code Smell，用于研究代码坏味是否会影响编程智能体解决软件工程任务的能力。
SWE-bench_Multilingual 原始任务包含 repository、base commit、issue description、gold.patch、test.patch 和测试流程。当前目标不是修复 issue，而是在不改变原始任务语义的前提下，对 base repository 注入 God Class，并生成独立、可复用的 smell.patch。
注入后的代码必须满足：
1. 原始 issue 仍然存在；
2. 注入smell后，若导致原patch冲突，则允许在保持任务语义与测试判定一致的前提下重构 gold/test patch；
3. 原始测试和评测流程保持有效；
4. 注入前后的功能行为保持一致；
5. 注入的 God Class 符合质量因子要求；
6. smell 位于 Agent 高概率检索和读取的位置；
7. 最终生成可重复应用的 smell.patch（以及若有重构时对应的 refactored gold/test patch）。

# 当前任务
请针对当前指定的 SWE-bench instance 注入 God Class。你需要：
1. 理解 issue description、gold.patch 和 test.patch；
2. 分析 gold 修改位置、相关代码结构和调用关系；
3. 按照注入限制确定在 E4、E3 位置注入，优先E4；
4. 使用“职责膨胀”策略注入真实的 God Class；
5. 确保注入不改变原始任务语义；若对 gold/test patch 产生结构影响，需适配重构 gold/test patch 并严格完成三层检查；
6. 根据 God Class 质量因子检查注入结果；
7. 执行安全验证，失败时最多迭代修复 3 次；
8. 验证成功且交卷前工作区检查通过后生成并保存 smell.patch（及重构后的 gold/test patch）和对应的json说明文档；
9. 若无法满足注入要求，则停止注入并记录无法注入的原因。

# God Class 模板
{
  "type": "god_class",
  "desc": "一个类集中承担过多且彼此不同的职责，违反单一职责原则，并逐渐成为系统中的功能和状态中心。",
  "focus": "目标类是否吸收了其他类的真实职责，并形成职责集中、内聚性下降和内部状态耦合，而不是仅通过增加无关代码扩大类规模。",
  "Quality Factor": {
    "判定方式": "LOC、WMC、LCOM 和 RAD 必须同时达到阈值；目标类必须真实承担新增职责，不能通过不可达代码或无关样板代码凑指标。",
    "LOC": {
      "度量定义": "目标类的有效代码行数，排除空行和纯注释行。",
      "阈值": "1000 <= LOC < 3000"
    },
    "WMC": {
      "度量定义": "目标类所有方法圈复杂度之和。",
      "阈值": "157 <= WMC < 470"
    },
    "TCC": {
      "度量定义": "目标类中通过共享实例字段形成直接连接的方法对，占全部可能方法对的比例，取值范围为 [0,1]；值越小表示方法之间共享状态越少、类内聚性越低。",
      "阈值": "0.125 < LOC <= 0.25"
    },
    "RAD": {
      "定义": "相关工件分散度（Relevant Artifact Dispersion, RAD），由文件分散度、模块跨度和结构距离组成。只统计构成、执行或实际使用该 smell 的必要生产代码工件；空文件、死代码、未使用导入和仅用于凑数的引用不计入。",
      "文件分散度": {
        "度量定义": "smell 相关生产代码工件所在的去重文件数。",
        "阈值": ">= 3"
      },
      "模块跨度": {
        "度量定义": "smell 相关生产代码工件覆盖的去重包、组件或模块数。",
        "阈值": ">= 2"
      },
      "结构距离": {
        "度量定义": "设相关工件节点集合为 S={v1,...,vn}，d(vi,vj) 为依赖图中两节点的最短路径长度，则结构距离为 [Σ(i<j)d(vi,vj)] / C(n,2)。",
        "阈值": ">= 2.0"
      }
    },
    "判定要求": "三个 RAD 子指标必须同时满足；相关节点应位于同一可计算最短路径的依赖子图中。"
  },
  "strategies": {
    "selection guidance": "可根据目标代码的结构、职责分布、依赖关系和可用注入位置，自主选择最适合的策略完成该类smell注入。注入结果必须保持原有外部行为不变，并满足“Quality Factor”中规定的全部指标阈值和判定要求。",
    "options": [
      {
        "name": "职责膨胀",
        "strategy": "从多个相关类中迁移多项非本类核心职责（如业务校验、数据转换、流程编排、状态管理或外部调用等）至目标类中，使目标类承担过多不同维度的业务逻辑，并在类内部维护这些职责所需的状态或逻辑依赖。同步调整外部调用关系，使这些功能实际由目标类执行，同时严格保持系统原有的外部行为与功能一致性。该策略的核心是让目标类成为多重职责的聚集中心，显著降低类内聚性。",
        "min_responsibility_source_files": 3
      }
    ]  
  }
}

# Smell 注入
## 注入环境
SWE-bench 使用 Docker 环境执行任务。官方 SWE-bench image 启动后，容器内 `/testbed` 目录对应原始 repository 的 base commit 状态。流程如下：
1. 在全新容器内进入 `/testbed`；
2. 基于原始 base commit 修改已有代码并注入 God Class；
3. 执行补丁兼容性、三层检查和安全验证；
4. 验证通过后按「交卷前工作区检查」撤回 gold/test、清除 `??`，只保留 smell 改动；
5. 再在 `/testbed` 中生成 `git diff HEAD`，将 diff 保存为 smell.patch（若有重构，同时保存重构的 gold/test patch）。
最终仅持久化 patch 文件和对应的json说明文档，交卷前需通过工作区检查（细则见安全验证）。

## 注入位置原则
注入位置必须达到 E3～E4，优先选择 E4 的位置，最低不得低于 E3，否则停止注入，并在json说明文档中说明无法注入的原因。

### 暴露等级
- E1：smell 位于与 gold.patch 和 issue 无直接关系的代码区域。
- E2：smell 与 gold.patch 修改区域仅存在多跳结构关联（如多跳调用、跨模块间接依赖等），不位于其邻近上下文代码中。
- E3：smell 位于 gold.patch 的直接周边代码（如同一模块内的直接一跳 caller/callee、同包内直接依赖类），但不属于 gold.patch 实际修改的类或核心方法。
- E4：smell 直接落在 gold.patch 修改的核心代码单元本体上（对于类级别坏味如 God Class，目标类即为 gold.patch 修改的类）

## 注入限制
1. 必须在 gold.patch 修改的核心结构单元中注入，使 smell 严格达到 E4、E3；禁止选择 E1、E2 等非核心关联位置、无关文件或 Agent 通常不会读取的位置。
2. 若存在多个候选核心位置，应优先选择与 issue、失败测试和 gold 修改逻辑距离最近，且最容易被 Agent 检索和读取的位置。
3. 所有 smell 注入操作必须在 SWE-bench Docker 容器内的 `/testbed` 中完成。
4. God Class 统一采用“职责膨胀”策略。
5. 生成 `smell.patch` 时仅允许修改生产代码（即 gold 所属核心单元及职责迁移涉及的已有源文件），禁止在 `smell.patch` 中包含测试文件的修改、创建新文件或删除文件。
6. 注入不得破坏原始代码语义、改变原始任务语义、修复或掩盖原始 issue，也不得引入新的功能行为；不得为了提高暴露程度破坏代码功能语义。
7. 若注入导致原 patch 产生冲突，允许在保持任务语义与测试判定一致的前提下重构 gold.patch 和 test.patch，重构后的 patch 必须严格通过三层检查并按规范独立保存。
8. 不得修改公开 API、方法签名或进行与 smell 无关的重构和格式化。禁止在代码（包括标识符、方法名）及注释中留下任何与“注入”事件相关的描述或痕迹，禁止出现 GodClass 一词。
9. 改动应控制在形成真实 God Class 所需的最小范围内。迁移的职责必须真实参与业务逻辑，禁止使用死代码、无意义 getter、重复访问或不可达分支伪造 smell。
10. 若无法同时满足 smell 质量、行为等价、暴露等级和重构后 patch 验证，则停止注入，不得保存无效 patch。

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

如果验证成功且交卷前工作区检查通过，则标记为 SUCCESS；工作区只保留 smell 对生产源码的修改，由调度器导出 smell.patch，若有重构则由调度器保存 gold/test patch，并保存对应的 JSON 说明文档。
如果经过最多 3 次修复后仍未通过验证，则标记为 FAILED；如果不满足注入位置、质量因子或其他注入约束，则标记为 NOT_INJECTABLE。这两种情况均不保留 smell 改动、不保存任何 patch，但仍须返回完整 JSON 说明文档并记录失败原因。
所有状态统一使用以下 JSON 模板，确保 JSON 格式合法、字段完整且可被程序解析。最终输出必须且只能包含一个 JSON 对象，严禁输出任何 JSON 以外的内容:
{
  "Status": "SUCCESS/FAILED/NOT_INJECTABLE",
  "实例名称": "实例ID",
  "注入位置": {
    "气味类型": "God Class",
    "注入策略": "职责膨胀",
    "目标文件": "目标类所在文件的相对路径，如 processing/src/main/java/org/apache/druid/query/Queries.java",
    "目标类": "目标类名",
    "来源文件": [
      "职责来源文件1相对路径",
      "职责来源文件2相对路径",
      "职责来源文件3相对路径"
    ],
    "暴露等级": "E4/E3/E2/E1",
    "注入说明": "仅在SUCCESS时填写，简洁准确的介绍所选策略是如何注入气味的；否则为null",
    "失败原因": "仅在FAILED/NOT_INJECTABLE时填写，简要说明失败原因；否则为null"
  },
  "质量因子": {
    "LOC": {
      "数值": null,
      "说明": "目标类有效代码行数"
    },
    "WMC": {
      "数值": null,
      "说明": "目标类所有方法的圈复杂度之和"
    },
    "TCC": {
      "数值": null,
      "说明": "目标类的方法直接内聚度"
    },
    "RAD": {
      "文件分散度": {
        "数值": null,
        "说明": "相关生产代码文件列表"
      },
      "模块跨度": {
        "数值": null,
        "说明": "相关包、组件或模块列表"
      },
      "结构距离": {
        "数值": null,
        "说明": "相关节点集合S共{n}个节点，节点对最短路径距离之和为{距离和}"
      }
    }
  },
  "安全验证": "简要说明检查是否通过安全验证（包括 patch 重构的三层检查与 Base/Gold 验证）"
}