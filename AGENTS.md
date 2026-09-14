# 项目持久上下文

## 修改本 Skill 的强制规范

用户明确要求：**所有对本 Skill 的修改必须严格遵循 `/Users/tachibanakanade/contract-govern-skil` 下的定义。**

开始修改前读取该框架的 `README.md`、`spec/SPEC.md`、`lifecycle/EVOLVE.md`、`lifecycle/TEST_POLICY.md`，复杂格式问题再查 `contract_governed_skill_agent_build_guide_v3.md`。这是维护协议；生产编排的唯一入口仍是本仓库 `SKILL.md`。

在 Windows 或其他 checkout 上，定位同一框架的本地副本：显式 `--framework`、`CONTRACT_GOVERN_HOME`、本项目同级 `contract-govern-skil`，按此顺序解析。不能把 macOS 绝对路径或旧的 `D:/contract-govern skill` 当作通用路径。找不到时明确报告缺失，不能跳过治理或换用另一套标准。

严格执行：新 requirement/claims → 明确 Router 插入点 → 新测试先运行并确认缺失行为失败 → impact → 修改 → 同步 interface/requirements/tests manifest → 新 skill.version → validate / contract-test / 全部 active 历史回归 → 真实代表性操作 → accept。

通过本项目 `scripts/govern.py` 运行外部框架，保护真实资产和部署配置。`changes/` 只允许成功的工具验收生成；不得手写成功记录、弱化历史测试或原地改写已接受的需求。保留测试首次失败和最终结果。外部框架源码只读，除非用户另行要求修改。

## 项目定位与约束

- Python 3.11+；Codex 负责意图、计划和美术判断，运行时执行确定性检索、校验、版本与审核门禁。
- Stage 1：先搜已配置资产库，再走 A 直接使用、B1 重贴图或 C 生成；结果进入审核。Stage 2：只用获批资产和程序化几何组装 Blender 场景。
- `ManifestManager` 是正式项目状态的唯一写入入口。返工保留旧版本，自动批准只能按用户授权启用，不能把文件有效当作美术批准。
- 默认 `plan_only`；Blender 默认 MCP。准备操作包和排队渲染不是构建完成，MCP 失败不自动切换 batch。
- 支持 macOS / Windows 自动路径和 Blender 可执行文件发现；项目数据采用相对路径，换机器后重新生成包含绝对路径的 MCP 操作包。详见 `docs/platforms.md`。
- Blender 最低 4.2，4.5 LTS 是当前部署基线；Blender 自带 Python、项目 Python、MCP Python、远程 HY3D Python 相互独立。
- 用户要求隔离环境：新用途需新建独立 Conda 环境，不污染 base、已有环境或系统 Python，不执行全局 pip 安装。已经建立的专用环境可按当前任务授权使用。
- 真正的主机、凭据和机器路径放在忽略的 `.env` 或宿主 MCP 配置中，不提交到共享模板。
- 既有 `projects/`、`.deps/` 和未提交的用户文件应保留，不把另一任务的改动当成自己的成果或覆盖它们。

## 已知事实与证据范围

截至 2026-09-13，本机是 Apple Silicon macOS。独立 Conda `two-stage-3d` 用于项目，`two-stage-3d-mcp` 用于 MCP。Blender 4.5.13 LTS 和 MCP 1.9.1 已完成真实操作包导出/渲染验证，记录位于忽略的 `.deps/blender-setup/SETUP.md`。这些只是本机证据，不能推断其他机器已安装或在线。

`projects/hy3d-smoke/` 有一次真实 shape 客户端测试产物；它不等于完整 Stage 1 门禁、审核和交付已通过。用户已选择完整 Stage 1 测试沿用其中 `input/demo.png`，参考图与生成结果的许可信息仍待补充，不能编造已核实许可。

生产 Schema 版本 `0.1`、Python 包版本 `0.1.0` 与 `interface.json` 的治理版本独立；当前正式接受状态以 `changes/` 最新工具记录为准。测试替身、回环 HTTP、宿主路径模拟和真实远程 GPU/Windows 实机验证必须分别描述。
