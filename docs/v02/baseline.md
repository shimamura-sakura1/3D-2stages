# v0.2 Phase 0 — v0.1 冻结基线

记录日期：2026-09-14。本文件描述进入 v0.2 重构前的 S4，不表示 v0.2 已实现。
起点为 Git `c8a9c12a3b5edc6dd7838911e44edc17c43ba0ba`、工具记录
`changes/change-005.json`（S3 → S4，2026-09-13）。本次只增加基线与治理证据；
生产 Schema 保持 `0.1`、Python 包保持 `0.1.0`，基线维护的治理版本为 S5。

## 使用范围与状态定义

生产唯一入口仍是 `SKILL.md` Execution Router。Step 1 使用本文件了解**已记录的证据范围**；
当前可执行能力和项目状态仍以当前 Runtime、Manifest 与最新接受记录为准。
此文是历史基线，后续阶段不能通过改写它把过去未实现的能力变成已完成。

| 状态 | 含义 |
| --- | --- |
| working | 表中明确限定的本地能力已通过本次执行；不外推其他平台、远程服务或美术质量。 |
| partially_working | 有真实实现和部分证据，但表中列出的集成或能力缺口尚在。 |
| unverified | 尚无该范围的充分验证；不等于实现不存在，也不等于已发生服务故障。 |
| not_implemented | 当前没有该能力的生产实现；文档、模板或协议接口不算实现。 |

测试替身、回环 HTTP、历史实机运行与本次实机运行分别标注。文件有效、渲染成功、
操作包准备完成都不能代替美术批准。`REQ-LIVE-001`、`REQ-ART-001` 保持 unresolved。

## 能力盘点

| 能力 | 状态 | 实现与证据 | 明确边界 |
| --- | --- | --- | --- |
| Manifest | working | `runtime/manifest_manager.py`；T-LEGACY-001、T-FLOW-*、T-PORTABLE-* | 唯一正式写入口、锁、版本及历史；这是应用层边界，不是 OS 沙箱。仅支持 0.1。 |
| State Machine | working | `runtime/state_machine.py`、`policies/stage_transitions.yaml`、ManifestManager；T-LEGACY-001 | YAML 是资产状态图；Scene/项目门禁另在 Manager/validators，尚非 Stage 0–3 高层状态图。 |
| Asset Search | working | `runtime/asset_search.py`、`providers/local_library.py`；T-LEGACY-001、T-STAGE1-E2E | 仅本地 catalog，真实文件复制；缺失 provider 或检索失败不能当成无候选直接生成。 |
| A/B/C Routing | working | `runtime/asset_router.py`、路由/许可 policies；T-LEGACY-001、T-STAGE1-E2E | A 直接使用、B 仅 B1 重贴图、C 生成；决策与许可门禁可用，不代表 B/C 远程 GPU 已验收。 |
| Stage 1 | partially_working | `runtime/stage1_executor.py`；本次本地 A 实例，B/C 回环 HTTP 测试 | 审核、返工、来源和交付生命周期已有实现；完整真实远程 B/C 生命周期未验证。 |
| HY3D Client | partially_working | `runtime/hy3d_client.py`；T-LEGACY-001、T-STAGE1-E2E；历史 shape smoke | 同步 HTTP、健康能力检查、Base64 GLB 回传已测；mock/回环结果不代表 GPU。仓库不含推理服务器或权重。 |
| SSH Transport | partially_working | `runtime/ssh_transport.py`；T-LEGACY-001、T-ENV-001 | 配置、隧道生命周期及拒绝行为已测，进程边界用替身；本次没有真实 SSH 连接。 |
| Stage 2 | partially_working | `runtime/stage2_executor.py`、`runtime/blender_worker.py`；T-LEGACY-001、T-PORTABLE-*；历史 Blender 运行 | 预检、导入、组装、输出校验已有实现；尚无独立 Blockout/LookDev/Render 和 StyleResolver。 |
| Blender MCP | partially_working | `runtime/blender_mcp.py`；T-LEGACY-001；历史 MCP 导出/渲染 | 默认 MCP；prepare/queued 不等于 built；需要宿主工具实际执行和 stage2-complete，失败不自动切换 batch。本次未连接或渲染。 |
| Delivery | working | `runtime/delivery_executor.py`；T-LEGACY-001、T-FLOW-*、本次本地 A 实例 | 获批资产打包、来源、快照、校验和；场景交付门禁/陈旧输入拒绝已由测试覆盖。本次不声称真实场景交付。 |
| Governance | working | `scripts/govern.py` → 指定外部框架；18 组原 active 测试、运行契约与静态校验 | 干净源码投影排除 `.env`、`projects/`、`.deps/`；框架只读；仅 accept 成功生成 change。 |
| 完整远程 Stage 1 + 艺术验收 | unverified | 历史 shape 只为直接客户端 smoke；REQ-LIVE-001/REQ-ART-001 未解决 | 参考图与生成输出许可仍待补充，不编造 license_verified，不发起额外生成。 |
| Windows 实机与当前外部连通性 | unverified | 路径/宿主发现模拟；历史 macOS Blender 证据 | 未进行 Windows 实机验证；doctor 只发现本地组件，不探测服务在线。 |
| 远程资产库、B2/B3、Stage 1 Route D | not_implemented | 只有 LocalLibraryProvider；Stage 1 的 route enum 仍为 A/B/C | Stage 2 已有 box/rail_track 程序化几何，不能算成 Stage 1 Route D。 |
| v0.2 Visual Planning / Style / Visual Critic / Revision Loop | not_implemented | 只有旧 style_bible 模板、单一 blender_plan 与人工审核入口 | 没有工业 ACG 可执行材质库、校准场景、语义材质映射、Preview pass 元数据或自动视觉回路。 |
| 并行 Worker 调度、Web 交付 | not_implemented | 角色边界/CLI 占位不能代替实现 | 没有并行调度；web 交付明确拒绝。 |

### 当前视觉实现的具体限制

`blender_worker.py` 给程序化盒体和轨道使用同一 `Shared matte palette`，
Principled roughness 固定为 `0.8`；导入 GLB 保留其已有材质。
当前仅建 SUN + 固定 world，使用 Cycles，camera/render 由单一计划提供。
这说明已有基础渲染能力，但还没有按材质类别解析参数、微表面变化和异源资产统一材质语言。
本次没有新渲染，不能把源码观察当成对新画面的视觉评分。

## 六类主要 Contract

所有路径均相对仓库。实际验证调用 `runtime/validators.py` 的 `validate_contract`，
还会按用途校验状态、许可、文件、摘要和审批。结构样例通过不能证明引用文件存在或艺术质量合格。

| 名称 | Schema | 内容和现有约束 |
| --- | --- | --- |
| manifest | `contracts/project_manifest.schema.json` | schema_version 固定 0.1；project_id、version、mode、brief、assets、supplied_assets、history、stage2、delivery、审批等。项目 state 为 planned/stage1/review_required/stage2/complete。 |
| asset_task | `contracts/asset_task.schema.json` | target/style/search/routing/hy3d/review、status、revision、result；保留独立资产状态与允许路线。 |
| stage1_result | `contracts/stage1_result.schema.json` | asset_id/revision/route/source/files/sha256/status/recipe；输出提交进入 review_required。 |
| blender_plan | `contracts/blender_plan.schema.json` | scene/assets/procedural/camera/lighting/style/render；listed assets 必须获批；程序化 kind 是 box/rail_track。 |
| review | `contracts/review_report.schema.json` | asset_id/revision/decision/issues/instruction/reviewer；决策 approved/revision_requested/failed；automatic 需要显式授权。它是资产审核，尚不是 v0.2 Visual Review。 |
| delivery | `contracts/delivery.schema.json` | target/files/attribution；打包前另查审批、现有文件和输入摘要。 |

只有 manifest 在这六类文件中显式带 `schema_version`；其余使用现有结构，
不能假定所有 v0.1 文档都带版本字段。结构 audit 另覆盖 `asset_candidate`，总计七类生产文档。
历史 Schema 摘要保存在 [evidence.json](evidence.json)；后续变更不得静默损坏 0.1 数据。

<!-- executable: baseline-contracts -->
```json
{
  "manifest": {"validator": "project_manifest"},
  "asset_task": {"validator": "asset_task"},
  "stage1_result": {"validator": "stage1_result"},
  "blender_plan": {"validator": "blender_plan"},
  "review": {"validator": "review_report"},
  "delivery": {"validator": "delivery"}
}
```

## 可执行基线示例

以下 JSON 是 `tests/test_v02_baseline.py` 实际执行的 CLI 参数与预期结果，
不是新 Runtime 协议。`PROJECT` 必须替换成**新建隔离技术样例**的路径，
从仓库根目录用专用 Python 执行 `runtime/cli.py`。不要套用到用户生产项目。

### 默认规划与拒绝门禁

<!-- executable: baseline-default -->
```json
[
  {"argv": ["init", "PROJECT", "--id", "baseline_default", "--brief", "Phase 0 isolated planning fixture", "--task", "templates/asset_task.yaml"], "exit": 0, "equals": {"mode": "plan_only", "auto_approve": false, "schema_version": "0.1"}},
  {"argv": ["run", "PROJECT"], "exit": 0, "equals": {"status": "plan_only"}},
  {"argv": ["stage1", "PROJECT", "--asset-id", "bench"], "exit": 2, "error_contains": "prohibited in plan_only"},
  {"argv": ["deliver", "PROJECT"], "exit": 2, "error_contains": "prohibited in plan_only"},
  {"argv": ["approve-final", "PROJECT"], "exit": 2, "error_contains": "Only a current, successful build"},
  {"argv": ["status", "PROJECT"], "exit": 0, "equals": {"state": "planned", "version": 0, "stage2.status": "not_started"}}
]
```

### 库资产、审核、返工和资产交付

仅使用仓库原创 CC0 长椅。这里的 `review` 是验证状态机的**合成审核输入**，
不是用户产品的艺术批准；不启用自动审核，不运行 HY3D 或 Blender。
测试另外比较两个版本的模型字节、来源、结果文件及交付快照，避免仅检查状态字符串。

<!-- executable: baseline-library -->
```json
[
  {"argv": ["init", "PROJECT", "--id", "baseline_library", "--brief", "Phase 0 isolated CC0 bench fixture", "--mode", "stage1_only", "--task", "templates/asset_task.yaml"], "exit": 0},
  {"argv": ["configure", "PROJECT", "--target", "asset"], "exit": 0},
  {"argv": ["approve-plan", "PROJECT"], "exit": 0},
  {"argv": ["stage1", "PROJECT", "--asset-id", "bench", "--catalog", "examples/library/catalog.yaml"], "exit": 0, "equals": {"route": "library_direct", "status": "review_required", "revision": 0}},
  {"argv": ["deliver", "PROJECT"], "exit": 2, "error_contains": "Required assets must be approved"},
  {"argv": ["review", "PROJECT", "bench", "--decision", "revision_requested", "--instruction", "Technical fixture only: reacquire to verify immutable revision history"], "exit": 0, "equals": {"assets.bench.status": "revision_requested"}},
  {"argv": ["stage1", "PROJECT", "--asset-id", "bench", "--catalog", "examples/library/catalog.yaml"], "exit": 0, "equals": {"route": "library_direct", "status": "review_required", "revision": 1}},
  {"argv": ["deliver", "PROJECT"], "exit": 2, "error_contains": "Required assets must be approved"},
  {"argv": ["review", "PROJECT", "bench", "--decision", "approved", "--instruction", "Synthetic review for isolated technical fixture; not production artistic approval"], "exit": 0, "equals": {"assets.bench.status": "approved"}},
  {"argv": ["deliver", "PROJECT"], "exit": 0, "equals": {"target": "asset"}},
  {"argv": ["status", "PROJECT"], "exit": 0, "equals": {"state": "complete", "stage2.status": "not_started", "assets.bench.revision": 1}}
]
```

## 本次测试与历史外部证据

实施前通过项目 `scripts/govern.py` 执行 validate、contract-test 和全部 test。
validate 无 error/warning；declared_contract 与 runtime_contract 均 pass。
全部原 18 组 active 测试重跑通过。首次沙箱运行失败于回环 HTTP bind 的 PermissionError，
涉及 T-LEGACY-001 的 1 个用例及 T-STAGE1-E2E 的 7 个用例；退出码 1。
经沙箱外授权重跑后通过，未改测试或生产源码来消除失败。
首次失败和通过结果均保留；详见 [工作记录](phase-0.md) 和 [证据摘要](evidence.json)。

历史实机证据只在其原日期与范围内有效：

- `.deps/blender-setup/SETUP.md`、`mcp-status.json`、`verification.json`：2026-09-13
  本机 Blender 4.5.13 LTS + MCP 1.9.1 实际导出/渲染并完成回收；不是本次运行。
- `docs/governance/S4.md` 与 `.deps/govern-s4/representative.json`：历史显式 batch
  自动发现 Blender、渲染、built；不代表 MCP 可自动退回 batch。
- `projects/hy3d-smoke/`：历史直接 shape 客户端产物，没有证明完整 Stage 1 门禁、审核和交付。
- `.deps/blender-setup/SETUP.md` 的路径检查、版本门禁、框架定位问题是**修复前记录**；
  S4 已实现对应修复，不能把那份旧文的“尚无检查”当成当前缺陷。

本次真实外部验证：**未执行** SSH/GPU 推理、Blender MCP/batch 渲染或 Windows 实机操作。
Phase 0 的代表性实际操作为上述隔离本地项目、模型文件复制、显式测试审核、返工和交付；
当前阶段不要求新增视觉系统或重新完成远程生产验收。

## Gate 0 与下一阶段

Gate 0 由现有回归记录、明确能力边界和本基线构成；本次维护变更还须通过 S5 治理 accept。
最终接受状态以 `changes/` 的工具记录为准，[phase-0.md](phase-0.md) 记录测试和审核结论。

下一步为 Phase 1 — Architecture Contracts First：新增 0.2 契约、区分 Manifest 版本、
表达 Stage 0–3 状态并安全迁移。当前未实现这些模块，也没有创建占位 Runtime。
后续顺序严格采用用户《Codex 分阶段重构执行计划》，架构规范是目标设计：
例如首轮六类材质、一个 overcast、默认最多 3 个 Preview passes 均按分阶段计划收敛，
不能因为架构示例有更多材质、灯光或 4 次迭代就提前扩展。
