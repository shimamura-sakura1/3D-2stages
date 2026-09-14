# Phase 1 — Architecture Contracts First

本阶段承接已接受 S5 / change-006。Phase 0 文件和历史证据保持原样；本文件只记录 Phase 1。
按照指定框架 README、SPEC、EVOLVE、TEST_POLICY，通过 `scripts/govern.py` 治理。

## Impact Analysis

新增 `REQ-V02-CONTRACTS-001`，五项 claims 分别覆盖：
1. 11类视觉文档和 Manifest 0.2 的真实结构 I/O；
2. 跨文档语义关联、路径、版本、Reference Role、Render/Review/Revision 一致性；
3. 与资产状态分离的 Scene 状态边检查；
4. 显式初始化和版本分流、旧执行器对0.2的拒绝、0.1默认行为保留；
5. 深拷贝旧数据的只读迁移预案，返回缺失输入，不授予新审批或修改旧文件。

Router 复用 Step 1 的 Read/Optional Tools，登记新 Contract 指导与审计脚本；
允许在 Step 1 完成契约任务后 END。Step 2 明确0.2不能进入旧生产执行器。
没有创建 Visual Director/Critic agent 或新的生产编排入口。

初始 impact 直接范围为 CLI、validators、ManifestManager、state_machine、Stage 1/2、
MCP、Delivery 与 SKILL；源码新文件同步登记实际依赖。外部框架只读。
新增注册没有扩大 `scripts/govern.py` 的源码投影范围；所有新增文件都在已有目录内。

## Files To Change

- `contracts/`：新增11类文档、独立 project_manifest_v02、visual_common 定义和 visual_audit_bundle。
- `runtime/validators.py`：精确版本分流、JSON有限值、时间检查、0.2 Manifest 语义校验与旧执行边界。
- `runtime/visual_contracts.py`：跨文档一致性、审批摘要验证和规范化内容 hash。
- `runtime/state_machine.py`、`policies/scene_transitions_v02.yaml`：独立场景图，只读检查。
- `runtime/planning.py`、`runtime/manifest_manager.py`、`runtime/cli.py`：显式0.2初始化/读取/迁移预案/状态边命令。
- `runtime/migrations/`：真实但只读的字段迁移；`pyproject.toml` 纳入子包，包版本不变。
- 原 Stage 1/2、MCP、Delivery：只增加版本门禁，0.1实现与协议不重写。
- `scripts/check_visual_contracts.py`：独立结构审计，拒绝重复 JSON key、NaN/Infinity。
- `tests/test_v02_contracts.py`、`tests/fixtures/v02/`：独立新测试/输入，旧文件和断言不改。
- `SKILL.md`、治理登记和本文档/证据：治理版本 S5 → S6。
- `changes/change-007.json` 仅允许成功 accept 生成。

## Contracts To Add/Modify

具体字段与限制见 [contracts.md](contracts.md)。旧 Contract 文件字节保持不变。
project_manifest_v02 的资产字段引用/复用旧0.1结构，资产获取语义改造留待 Phase 4。
新公共契约审计有真实 runtime binding，输入为完整 bundle，输出为12份校验后的 JSON，
同时有有效/无效输入证据及结构化错误协议。visual_common 是共享定义容器，没有独立生产文件。

## Tests To Add

先建立 fixture 和测试，生产实现前确认缺失能力失败。首轮35 failed / 10 passed；
发现10个负例仅因 Unknown contract 而通过，为这些测试加“合法文档先通过”的前置断言，
第二轮45 failed，确认为缺失 Schema/命令/模块所致。两轮日志都保留。

实现后45项通过；进一步补充直接执行器门禁、Manager权限/初始化覆盖拒绝、
当前审批摘要、已交付旧项目迁移、重复JSON和文档索引等边界。
56项中2项失败：Manifest索引未对齐实际文档摘要，以及当前环境缺少 JSON Schema 可选
RFC3339检查依赖导致 format=date-time 未生效。先记录失败并再做 impact，
补上显式索引校验和不依赖额外安装的时间格式检查，最终56项本地测试通过。

收尾审查补充3个时间边界，发现 Python 的 ISO解析会接受不带冒号的紧凑时间，
与 Contract 要求不一致；新增用例先出现1 failed，保留日志并再次 impact 后，
增加明确的带时区时间语法检查及日期合法性检查。最终59项通过。
新增正则只检查时间字符串语法，不做自然语言语义分类，也不引入新的依赖。

场景图检查遍历15×15对状态，合法边通过、其余拒绝；旧资产状态机另行验证未被混入。
审批测试证明旧场景版本、过期摘要和最近一次拒绝不能满足批准。
测试是结构/边界证据，不是对 fixture 图片的真实视觉评价。

## Backward Compatibility Risk

风险集中在全局版本校验和旧入口可能误吃0.2字段；通过保留全部旧 Schema、精确分流、
显式 init-v02 及直接执行器/Manager 两层门禁控制。
默认 init 及其原 runtime binding 仍只服务原入口测试，不添加改变该输出范围的 schema flag。
不把旧项目 auto_approve 授权迁移到新的视觉范围，也不把旧 style_bible 猜成新的 Style Profile。
原审批、版本、来源、返工历史在 legacy_manifest 中完整保留，源文件只读。

## Implemented

11类视觉 Contract、独立0.2 Manifest、完整结构 I/O审计和关联校验、15态场景边检查、
显式初始化/状态查询、只读字段迁移及缺失输入报告，均有真实实现。
Stage 0–3可以被契约表达；尚不能在0.2项目上执行这些生产阶段。

## Not Implemented

Style Profile Schema/注册/解析、Shader、Lighting Rig、Stage 0生产、Route D、
LookDev执行、Preview流水线、Visual Critic AI、自动Revision和可安装迁移均未实现。
不存在新空壳视觉模块；迁移是可调用的字段转换函数，不是已安装的完整新项目。

## Tests Executed

最终 validate=pass，warnings=[]；contract-test 的 declared_contract 和 runtime_contract 均 pass。
`test --requirement REQ-V02-CONTRACTS-001` 共21/21 active组通过，包含全部19组历史测试、
新增59个用例及新审计工具的有效/无效运行I/O。先前通过与失败的报告均保留。
9条历史需求、19条历史测试登记、历史测试代码、原Schema字节及Phase 0文档都未改。
最终静态、真实运行契约、全体 active 历史回归和 accept
以 [phase-1-evidence.json](phase-1-evidence.json) 及工具生成的 change-007 为准。
日志保留在 `.deps/v02-phase1/`、`.skillctl/reports/`；不覆写失败证据。

## Real External Validation Executed

Phase 1不涉及美术执行，本次不发起 SSH/GPU、Blender MCP/batch或 Windows实机任务。
代表性实际操作使用隔离本地目录：创建新0.2项目、读状态、对真实旧库资产项目生成迁移预案、
核对旧项目全部文件摘要、校验工业站台完整文档并实际导出12份JSON、检查合法与非法状态边。
本次核对源项目20个文件均未改变，实际检查路径中的16条合法边和一条跳步拒绝。
新项目状态仍 initialized，迁移结果仍 migration_required_input，不产生任何隐含审批。
审计 fixture 中渲染和评论字段只是结构样例，不能当作真实渲染/视觉评价的成功证据。

## Known Limitations

Scene edge checker没有写状态能力；批准记录校验是数据一致性检查，不是身份认证。
Revision上限在本阶段限制拟定计划，真正执行循环及跨运行次数管理留待 Phase 8。
只读迁移缺少四类视觉输入，候选Manifest不可安装，不能复制草案替换生产Manifest。
外部服务、完整远程Stage 1、Windows实机和美术质量证据范围与Phase 0相同。

## Next Phase Readiness

`Next Phase Readiness = READY`：Gate 1的11类视觉文档、Stage 0–3场景状态表达、
0.1/0.2精确区分、只读迁移与兼容门禁已有实际实现和证据；全部历史回归与代表性操作通过。
人工语义审查确认没有削弱既有审批、来源、版本约束，没有把状态边检查、迁移草案或
结构 fixture 中的渲染/评论数据当成实际生产完成。
S6正式接受必须以工具成功生成 `changes/change-007.json` 为准；本记录不代替 accept。
验收后进入 Phase 2：Style System Foundation，第一轮六类材质、一个overcast和真实校准渲染。
本次停在 Phase 1 边界，不提前实现 Phase 2。
