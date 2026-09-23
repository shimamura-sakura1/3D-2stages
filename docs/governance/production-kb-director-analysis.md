# 场景生产视觉任务：职责与实施映射

本文替代早期“缺少专业实现就阻塞”的接入建议。当前设计由本 Skill 提供场景规划、视觉判断、制作、评审、受限修订与追踪；具体执行选择是内部机制。main 始终负责拆解任务、读取实际图片、接纳结果及决定下一步。可选实现或知识缺失不阻塞默认路径；明确指定不可用实现、输入错误、约束冲突和过期结果须准确拒绝。

## 生产职责

| 插入点 | Agent 决策 | 运行时边界 | 下一步 |
| --- | --- | --- | --- |
| Step 2 | 识别当前工作、核实运行证据、恢复进度 | task record、输入基线、已有 job/receipt、重复提交保护 | 当前未完成步骤 |
| Step 5V | 基于实测结构和 Style 制定 camera/composition/lighting/atmosphere，明确柔度与雾的执行解释 | create_direction、编译、计划原子接纳、AABB 相机求解、获批几何保护 | 原 Step 6V 实际渲染 |
| Step 7V | 查看指定实际 PNG，记录发现/成功决策，独立填写九类生产评审 | review_render 的图像/方向绑定；与生产诊断原子接纳 | 原 Step 8V 或最终审核 |
| Step 8V | 据当前评审提出合法子方向、保持项、动作和幅度 | refine_direction、差异白名单、父方向、保持项和预算 | 原 Step 6V |
| 最终审核 | 向用户展示真实图片和当前诊断 | 不可变完成凭据、已接纳任务证据、用户最终决定 | 获批后才可交付 |

这五个开发阶段没有增加生产阶段，也不建立第二份流程入口。生产流程唯一入口是 SKILL.md；interface.json 登记真实文件、绑定、依赖及条件能力。

## 分阶段文件与修改

| 阶段 | 涉及文件 | 修改 |
| --- | --- | --- |
| S26 / REQ-VISUAL-TASK-001 | runtime/visual_tasks.py；runtime/cli.py；runtime/manifest_manager.py；runtime/visual_contracts.py；contracts/project_manifest_v02.schema.json | 准备/开始/查询/提交任务，ManifestManager 持有正式写入权；候选结果不推进阶段；输入与结果摘要检查 |
| S26 | contracts/visual_task_{request,brief,scene,style,knowledge,scene_state,references,direction,review,error,record,command,result}.schema.json；docs/v02/contracts.md | 分离公开视觉数据与生产私有记录；真实 stdin/stdout/error 边界；旧项目可省略任务区 |
| S26 测试 | tests/test_visual_task_contracts.py；tests/test_visual_task_io.py；tests/fixtures/visual_tasks/ | 合法输入、结构化拒绝、身份/路径/过期写入、真实子进程 I/O |
| S27 / REQ-VISUAL-LOCAL-001 | SKILL.md；prompts/parent.md；prompts/visual_task_{direction,review,refinement}.md；prompts/render_critic.md | main 自行执行完整视觉任务；看实际图；定性 severity 不自动变分数；空建议不是返工 |
| S27 | runtime/render_context_builder.py；runtime/style_registry.py；runtime/render_direction_adapter.py；runtime/scene_production.py；runtime/manifest_manager.py；runtime/revision_controller.py；runtime/render_director.py；runtime/cli.py | 分离投影与 semantic 摘要；自由场景类型的新路径；复用求解器、显式执行选择；当前计划/图像/父方向/动作绑定；旧协议分支保留 |
| S27 | contracts/visual_compile_request.schema.json；contracts/lookdev_plan.schema.json；contracts/render_plan.schema.json；docs/v02/{production,visual-review,controlled-revision,style}.md | 编译输入及可选任务绑定；与生产门禁的关系；支持和拒绝范围 |
| S27 测试 | tests/test_visual_task_{context,compile,local_flow,revision}.py | 上下文来源、执行选择、计划进入生产、空建议、谱系/幅度限制 |
| S28 / REQ-VISUAL-OPTIONAL-001 | runtime/visual_task_adapter.py；runtime/knowledge_resolver.py；runtime/visual_tasks.py；runtime/env_config.py；scripts/setup_dev.py | 按真实 schema/文件/依赖选择实现；串行 file-task 调用信息与结果收集；只读指定 canonical items、按 operation/renderer/scene 过滤 |
| S28 | contracts/visual_execution_config.schema.json；contracts/visual_knowledge_{item,pack}.schema.json；docs/v02/visual-task-adapters.md；docs/v02/render-director.md；docs/development.md；SKILL.md | 宿主配置、当前可选协议与历史兼容协议分开；基础开发不要求固定外部旧版本；配置不含凭据 |
| S28 测试 | tests/test_visual_task_{selection,adapter,knowledge,setup}.py | 实现有无 × 知识有无四种组合；显式缺口拒绝；不适用 refine 的知识不传入 |
| S29 / REQ-VISUAL-RESUME-001 | runtime/visual_tasks.py；runtime/visual_task_adapter.py；runtime/manifest_manager.py；runtime/visual_contracts.py；runtime/cli.py；contracts/visual_task_record.schema.json | 重用未完成任务、查询下一动作、先收集现有输出、确认中断后接手、三次尝试上限；正式接纳时原子固化来源记录 |
| S29 | SKILL.md；prompts/parent.md；docs/v02/preview.md；docs/v02/task-tracking.md | 持续报告完成/进行中/阻塞/下一步；先恢复任务与已有渲染，再考虑新尝试 |
| S29 测试 | tests/test_visual_task_{resume,atomicity}.py；test_visual_task_adapter.py | 重复准备/派发/提交、并发写入、输入基线与进度版本、已有结果收集、来源不可篡改 |
| S30 / REQ-VISUAL-RELEASE-001 | README.md；SKILL.md；docs/v02/{quickstart,production,delivery}.md；docs/development.md；runtime/visual_delivery.py；scripts/export_production.py | 文档说明自身能力；交付只收录正式接纳的声明文件；消费者包去除可选实现硬依赖与开发资料 |
| S30 测试 | tests/test_visual_task_{delivery,distribution,examples,end_to_end}.py | 交付证据与候选隔离、消费者完整性、命令示例、集成生产门禁 |
| 每阶段共同文件 | requirements.json；interface.json；tests/manifest.json；本文；.skillctl/reports/ | 独立需求/claims、真实依赖与覆盖映射、首次失败/影响/最终结果。成功 changes 只能由最终 accept 生成 |

runtime/visual_review.py 原有图像与九类检查继续复用；任务接纳在 ManifestManager 同一事务中调用 visual_tasks.accept_review，未复制或削弱旧图像验证。新方向当前只支持 camera framing、灯光方向/fill ratio 和 fog 的受限修订；roughness/exposure 等旧动作仍留在兼容路径。不可执行的组成调整不会假装已完成。

## 证据与限制

开发声明 S26—S30 不等于 accepted；基线声明 S25、最新既有正式记录 S23。此前 unresolved 需求未改写。所有既有测试和 fixture/helper 保留，新测试使用新的 visual_task_helpers.py，合成 PNG 与审批夹具明确标记为测试替身。

首次失败及阶段运行保存在忽略目录并汇总到 .skillctl/reports/。阶段 1—4 的首次失败分别验证缺失入口/编译绑定/可选选择/恢复能力；阶段 5 首次失败暴露旧生产硬依赖以及新测试缺少完成证据。后者修正新夹具的 setup/blockout/PNG 尺寸和真实完成接口使用，未弱化交付门禁。新增来源不可变断言也先确认失败，再实现原子快照。

实际 Blender 验证使用独立工程项目，前置审批是显式测试夹具，不是用户美术决定。只有真实 Blender 测量、渲染 receipt、已查看 PNG 与 Agent 评审才能作为当前本地视觉路径的技术证据。最终用户审批与艺术质量不由测试代替。具体结果及文件摘要见本次 .skillctl/reports/ 记录；外部专业实现的真实艺术闭环不由四组合测试替身证明。

静态 POTENTIAL_SILENT_DEFAULT 警告需人工审查：旧求解器的默认值保持历史兼容；新任务中可选资料/执行配置的空值是显式默认 main 的需求，缺失生产身份、必需输入、错误输出、显式 unavailable 和过期基线仍拒绝。运行时不把定性方向猜成执行值。

共享源码不保存实际宿主安装目录或凭据。开发分支 dev/v3 保留维护资料；发布工具只导出消费者文件到 main，不合并整个开发树。外部 Skill、知识库、框架与现有用户项目均不属于此次修改范围。

## 本次实测结果

- 53 项阶段相关测试通过；补齐三操作夹具、路径越界及连续修订恢复交付后，13 项相关检查通过（与前者部分重叠，不能相加作唯一测试数）。
- Blender 5.2.1 LTS 在 2026-09-19 生成两张实际 PNG；第二张于 2026-09-23 恢复会话后完成看图和任务评审。填充光比例从 0.25 改为 0.15；几何摘要两次均为 `59561de760c95b51656a8ca8ed158d5982af2b5b70a0fe569c4109f9415402a0`。
- 第一张 PNG SHA256：`66157a9fc1b5d11653773c7e34dee513e71c88233f41cbeb45e832ff0786a61f`；第二张：`3ef7064bbf5edfea22d7722a1c7c3fc9226cd9327caffdd084936c6f095ca69d`。
- 四个任务（创建方向、评审、修订方向、再评审）均由 main 执行并正式接纳。工程项目停在 `final_review_required`，未记录最终用户批准，未交付。该证据验证 main 的技术闭环，不代表场景美术质量已获用户认可。
- `.skillctl/reports/visual-s26-s30/live-evidence.json` 保存范围、日期、task 状态、摘要和限制；首次失败及阶段报告保存在同目录。正式 accepted 状态以最后由工具生成的 change record 为准。

## 正式验收失败后的修正

首次正式 accept 的声明契约与运行时契约通过，55 组测试中三组未通过，没有生成成功记录。
交付资源组的九个失败来自本机临时目录拼接后超过 Windows 普通路径上限；改用忽略目录 `.deps/t` 后，原样运行 `tests/test_v02_delivery_resources.py` 的 11 项全部通过，没有修改历史测试或生产实现。

另外两组原有断言全部通过，但缺少所登记的实际读取/执行证据。最新正式 S23 记录尚未包含这两项 S24 登记；保留它们的 claims、exercises 和原测试，追加以下验证：

| 登记 | 新文件 | 实际验证 |
| --- | --- | --- |
| T-RENDER-DIRECTOR | tests/test_visual_task_legacy_cli.py | 子进程生成旧上下文、提交旧方向并核对存储结果；错误项目身份被拒绝且状态不变 |
| T-CONSUMER | tests/test_visual_task_consumer_guides.py | 读取平台与兼容指南源文件，对比发行副本，解析其中命令示例并核对链接及兼容范围 |

新增两项检查通过。首次失败、修正后的相关结果和最终正式验收分开保存；没有删除验证义务或修改已接受的历史测试。
