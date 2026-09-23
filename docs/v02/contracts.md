# Phase 1 — v0.2 Contract 边界

本页定义 Phase 1 的数据语言与确定性校验边界，早期阶段记录不作为当前能力清单。
新视觉场景从 [v0.2 quickstart](quickstart.md) 进入：现已支持 Stage 0、版本化 Style、
Geometry、分离式 LookDev/Render、视觉评论和受限返修，具体执行条件见各阶段指南。
v0.1 继续作为兼容路径；新视觉场景的旧入口已 deprecated，旧命令行为与历史测试保留。
Schema 合法或状态边合法始终不等于操作已执行、用户已批准或完整交付已实现。

## 版本与入口

从 `SKILL.md` Router Step 1 进入。默认 `init` 及原运行契约仍输出 Manifest 0.1。
显式选择 `init-v02` 才建立 0.2，状态为 initialized、mode=plan_only、auto_approve=false，
没有审批、资产或已建场景。所有正式 Manifest 写入仍经 ManifestManager。

```text
python -m runtime.cli init-v02 PROJECT --id station --brief "Industrial station"
python -m runtime.cli status PROJECT
python -m runtime.cli scene-transition-check render_review_required visual_revision
python -m runtime.cli migrate-v02 LEGACY_PROJECT
```

`PROJECT` 应为新路径。`scene-transition-check` 不接收项目路径，只检查一条边，
返回 execution=not_performed。`migrate-v02` 只读旧项目，stdout 返回迁移草案和缺失信息；
它不安装、复制或改写项目。新视觉场景后续生产使用对应 v0.2 专用入口，参见 [Production](production.md) 与 [Preview](preview.md)。
对 0.2 使用旧 run/approve-plan/approve-final/review/configure/stage1/stage2/deliver 等操作会明确拒绝，
直接调用旧执行器和 Manager 变更入口也不能绕过。

## 文档与职责

11类视觉文档都要求 `schema_version: "0.2"`、project_id、scene_version、document_id、revision。
scene_version 从1开始，表示场景版本；revision 从0开始，表示文档修订；Manifest.version
是正式状态写入的并发版本，三者独立。新 Schema 位于 `contracts/`，旧 Schema 文件不改。

| 文档 | 职责 | 拒绝的典型输入 |
| --- | --- | --- |
| visual_brief | mood、视觉语言、优先级、约束 | Blender 数值字段混入语义意图、未知顶层字段 |
| reference_board | 图片路径、明确 roles、权重、来源声明 | everything、跨项目路径逃逸、重复 reference_id |
| scene_spec | 米制尺度、对象关系、重复、景深层次、视觉焦点、语义摄影意图 | 不存在的对象引用、重复对象、未知焦点 |
| style_assignment | 风格版本及 lighting/atmosphere/camera/color profile 引用 | 引用不存在或越出该 reference 的声明角色 |
| blockout_plan | geometry_source、asset_id、变换、层级、重复和间距 | 缺失对象、重复放置、循环父子关系、非程序化对象缺 asset_id |
| semantic_material_map | 对象/slot → material_class、condition、surface_source | 不存在的对象、重复 slot、未知材质类 |
| lookdev_plan | style_assignment/material_map 引用及语义灯光、氛围 | 文档 ID 或 profile 关联不一致 |
| render_plan | renderer、camera、分辨率/采样、颜色管理和输出路径 | 非正采样、摄影机位置等于目标、非法路径 |
| render_metadata | build/pass/scene、渲染计划 hash、图像 hash、时间和成功/失败 | 无时区/非法时间、成功但缺图像；visual_approved 不属于本 Contract |
| visual_review | 对指定渲染图的9类主观评价、诊断和建议 | 分数越界、图像或 Render Metadata 不一致 |
| revision_plan | 指定 review/render 的下一 pass 与6类受限动作 | 任意 Python、昂贵几何替换、未推荐动作、越过 pass 上限 |

材质类的 Contract 词汇预留 painted_metal/bare_metal/concrete/rubber/glass/emissive/asphalt/vegetation；
这不等于八套材质都可执行。1.0.0 实现前六类与 overcast；显式 1.1.0 增加 vegetation 和细化签名，见 [Refinement](style-refinement.md)。
style profile 允许 `profile_version: planned` 表达尚无执行资源，校验不宣称该 profile 可以加载。
Reference 的 license_verified=false 可保存未核实来源，不构成生产使用许可或生成授权。

Revision Contract 第一版只允许 roughness_variation、lighting_intensity、lighting_direction、
fog_amount、camera_framing、exposure。Critic 可建议 replace_geometry/regenerate_geometry，
但这两类不能进入此自动 Revision Contract；以后须走重新审核路径。
max_preview_passes 最大3，包含 pass_00 初始预览；revision 的 pass_index 为1或2，
必须小于该上限且是所评论 pass 的下一次。本 Contract 只校验拟定动作；当前执行和 pass 上限门禁由 [Revision Controller](controlled-revision.md) 实现。

## Manifest 0.2 与状态机

独立 Schema 为 `project_manifest_v02.schema.json`；`validate_manifest` 按确切版本分流，
缺失或未知版本拒绝。旧 `project_manifest.schema.json` 仍只接收0.1，不静默套用新字段。
0.2 保留资产自己的旧 Contract/状态，新增 scene_version、artifacts、approvals、
legacy_manifest、migration_required_input；没有把资产状态和 Scene 状态合并。

主要路径：

```text
initialized → visual_planning → visual_review_required → visual_approved
→ geometry_pending → geometry_review_required → geometry_approved
→ blockout_pending → lookdev_pending → render_pending → render_review_required
→ final_review_required → approved → delivered
```

返修边：视觉待审可回 visual_planning；几何待审可回 geometry_pending；
render_review_required/final_review_required 可进入 visual_revision，再回 lookdev_pending 或 render_pending。
合法边详见 `policies/scene_transitions_v02.yaml`。跳步、自环、未知状态拒绝；
`policies/stage_transitions.yaml` 继续只用于旧资产状态图。

状态边合法不表示前置材料齐备，也不授予审批。
Manifest 中 visual/geometry/final 批准记录必须由 user 类型声明，绑定当前 scene_version 和
对应文档 hash；新状态需要这些证据，旧版本、过期 hash、最近一次拒绝都不能满足审批要求。
几何批准还要求全部 required 资产 approved 并绑定资产摘要。
这些是表示层一致性检查，不是用户身份认证，也没有公开“任意设置 v0.2 状态”的写入命令。
初始项目禁止预置审批/资产/迁移内容；各阶段通过专用写入方法执行，不能开放任意 dict 更新。

artifacts 的每条记录保存 document_id、revision、scene_version、相对路径与内容摘要，
多个修订使用不同路径。摘要算法为 UTF-8 编码、键排序、紧凑分隔符的标准有限 JSON 的 SHA256
（`runtime.visual_contracts.document_hash`）；不是 YAML 文件原始字节摘要。
资产模型的 sha256 仍是原来的文件字节摘要。

## 只读迁移

`runtime/migrations/v01_to_v02.py` 只转换安全、明确的字段：project_id、user_brief、
assets、supplied_assets 深拷贝到候选0.2；完整旧 Manifest 深拷贝到 legacy_manifest，
保留历史、来源、审批、style_bible、delivery 和既有配置。

旧 style_bible 无法自动推出四份 Stage 0 文档，因此返回：

```text
status = migration_required_input
required_inputs = [visual_brief, reference_board, scene_spec, style_assignment]
source_modified = false
```

新视觉范围保持 initialized / plan_only / auto_approve=false / approvals=[]，
旧审批只作为旧范围证据保留。原项目文件、审核、交付包和 MCP 操作包都不改动。
候选中的相对路径仍指向原项目数据；候选不是独立完整项目，不能复制一个 manifest 就声称迁移成功。
当前迁移仍不安装该草案、不提供回写或就地升级。可执行只读示例见 [quickstart](quickstart.md)。
移动主机后旧 MCP 绝对路径仍需重新生成，不能因迁移预案通过就复用。

## 真实结构 I/O 审计

`scripts/check_visual_contracts.py` 读取 stdin JSON，检查完整 bundle 的11类文档、Manifest及
声明的状态边，在空输出目录写出12份经过校验但内容不变的 JSON。数据及关联检查完成后才写文件；
无效输入返回退出码2和结构化 error，不产生输出。已有非空输出目录拒绝覆盖。

```text
python scripts/check_visual_contracts.py --output NEW_AUDIT_DIR < YOUR_AUDIT_BUNDLE.json
```

输入 bundle 应包含完整、相互一致的项目文档；结构检查本身不生成图片或评价画面。
审计核对跨文档 ID/版本、reference roles、几何层级、材质指向、render hash、review 图像和 revision。
它不检查每张引用图片实际存在、不加载 Shader，也不替代生产资产许可和文件完整性验证。
输出 status=valid / approval_granted=false / execution=not_performed。

外部视觉方向与本地计划的数据关系见 [Render Director 接入](render-director.md)。

## Uniform visual task contract

The `visual_task_*` schemas describe separated intent, measured structure, sourced Style priors, optional knowledge/observations/references, and three operation requests. Public direction/review results contain visual decisions; production identity, executor, input hashes, attempts and result references live in the production task record. `visual_task_command` / `visual_task_result` / `visual_task_error` describe the real stdin/stdout/stderr tool boundary. `python runtime/visual_tasks.py` accepts a JSON command; `{"command":"capabilities"}` is a read-only discovery example.

Existing project manifests may omit `visual_tasks`. New task records are written only through ManifestManager with expected_version. A prepared task does not alter approvals or production stage. Candidate results must pass the existing plan, review or revision operation before becoming accepted. Old production schemas and historical direction files keep their original meaning. See [task tracking](task-tracking.md).
