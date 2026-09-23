# v0.2 离线视觉规划入口

新视觉场景从 `SKILL.md` 的 Step 1 → Step 0V 进入，使用本页的 v0.2 流程。
在仓库根目录、已安装本项目依赖的独立 Python 3.11+ 环境执行；环境安装和跨平台发现见
[平台说明](../platforms.md)。命令不要求 Blender、MCP、SSH 或 HY3D 在线。

使用尚不存在的 `projects/v02_demo`。四份 Stage 0 文档在
[`templates/v02_stage0.yaml`](../../templates/v02_stage0.yaml)，场景为前景站台、中景设备与背景墙面。
模板显式选择 `industrial_acg_v1` 的 **1.1.0**；默认风格版本仍是 1.0.0。
参考图为本仓库新绘制的 SVG 材质示意图，其来源及许可证据见
[`examples/v02/LICENSE.md`](../../examples/v02/LICENSE.md)。它仅承担 `material_language` 角色，
不表示用户认可构图或风格，也不证明最终渲染质量。

<!-- executable: v02-stage0 -->
```text
python -m runtime.cli init-v02 projects/v02_demo --id v02_demo --brief "Quiet industrial station with matte teal equipment and warm concrete"
python -m runtime.cli reference-add-v02 projects/v02_demo examples/v02/reference.svg --id ref_material --role material_language --source examples/v02/reference_source.yaml
python -m runtime.cli stage0-submit projects/v02_demo --proposal templates/v02_stage0.yaml --expected-version 0
python -m runtime.cli status projects/v02_demo
```

预期最终 Manifest：`schema_version=0.2`、`version=1`、`scene_version=1`、
`state=visual_review_required`、`mode=plan_only`、`auto_approve=false`、`approvals=[]`。
四份文档保存为 `stage0/rev_0000/` 下的不可变文件，Manifest 索引其内容摘要。
参考原始字节复制到 `references/selected/ref_material-<SHA256>.svg`，模板中的路径与本例实际字节相符。
没有 Stage 1 获取、Blender 构建、渲染、用户批准或交付。此处停下，展示具体方向供用户审核。

只更换项目目录时保持 `--id v02_demo` 即可重复演示；要使用自己的项目 ID，应先复制模板，
同时修改四份文档的 `project_id`。替换图片后使用 import 返回的新路径和真实来源声明更新副本，
不可沿用本例 SHA256 或把本例 CC0 声明套给用户图片。未知权利应如实记录；导入不授予使用许可。
提交绑定当前 Manifest.version；过期版本、身份不匹配或图片字节被修改都会拒绝，不能靠编辑 Manifest 绕过。

用户明确决定后，才通过 `visual-review-v02` 记录当前快照的审核；本页没有自动批准命令。
后续授权获取见 [Geometry](geometry.md)，分离式组装见 [Production](production.md)，
真实预览回收见 [Preview](preview.md)，评论与受限返修见 [Critic](visual-review.md)、[Revision](controlled-revision.md)。
准备操作包或排队渲染不表示完成；视觉评论也不替代用户最终审批。

## v0.1 兼容与只读迁移

`init` 保留 0.1 行为，旧 `run/stage1/stage2/approve-plan/approve-final/deliver` 继续用于既有 0.1 项目。
这些入口作为新视觉场景的首选路径已 deprecated；兼容代码及历史测试仍保留。
它们对 0.2 项目明确拒绝。旧版本概览与早期阶段证据是有日期的历史范围，不是当前能力清单。

将 `LEGACY_PROJECT` 替换为现有 0.1 项目目录（例如已跑通的 `projects/readme_demo`）。
本命令只读取并将 JSON 草案输出到终端，不安装候选项目，也不改写来源、审核、交付或 MCP 操作包。

<!-- executable: v02-migration -->
```text
python -m runtime.cli migrate-v02 LEGACY_PROJECT
```

结果为 `migration_required_input`，缺失项是四份 Stage 0 文档。
`candidate_manifest` 深拷贝资产、供应资产和需求，并把完整原 Manifest 放入 `legacy_manifest`；
新视觉范围为 `initialized / plan_only / auto_approve=false / approvals=[]`。
旧审批只保留在旧范围；候选相对路径仍依赖原项目数据，不能把候选 Manifest 当作完整迁移安装。
迁移不会推断四份视觉设计或给新范围批准。跨主机使用时必须重新生成包含绝对路径的 MCP 包。

通用资产许可规则仍为已核实 CC0/CC BY；官方 Hunyuan3D-2.1 生成输出有独立且限定的
[provenance 支持](../hy3d-provenance.md)，不能把该输出标成 CC0，也不能扩展至库资产或参考图。
`doctor` 是本机发现，`hy3d-health` 是服务协议探测，二者都不是推理或渲染结果。
实际机器状态与日期证据分别记录；离线示例不证明远程 GPU、Windows 实机或美术验收通过。

## From a new scene to delivery

Main refines the brief and asks for missing decisions, prepares the scene breakdown and records explicit visual approval. It acquires and reviews geometry, measures the approved scene, authors a structured visual direction, compiles plans, executes Blender setup and renders a real preview. It views that image, records the nine-category diagnosis and performs only supported, budgeted refinements. Final delivery follows explicit user approval. [Task tracking](task-tracking.md) preserves progress across sessions; no additional visual implementation or knowledge collection is needed for the basic workflow.
