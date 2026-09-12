# Two-Stage 3D v0.1

根据 `two_stage_3d_skill_codex_spec_v0.1.md` 实现的 **Phase 1 MVP**。
核心是可审核、可返工的两阶段运行时与 Codex Skill。

当前部署约定：**Codex 通过 MCP 控制 Blender；HY3D 在远程 GPU 服务器推理，通过 SSH 隧道接入。**
服务器尚未准备，连接配置位于 [configs/hy3d_ssh.yaml](configs/hy3d_ssh.yaml)，实际主机、用户名、密钥路径、端口、网关地址和令牌只放在已忽略的根目录 `.env`。
详见 [Blender MCP 与远程 SSH 接入说明](docs/mcp_and_ssh.md)。

## 修改与迭代 Skill

本项目已按 Contract-Governed Skill 的 MIGRATE 流程增加治理元数据，保留原有业务目录。
从 [迭代步骤](docs/governance/EVOLVE.md) 开始：先新增需求/断言及测试，再做影响分析、修改和回归，最后接受版本。

- `SKILL.md`：真实 Execution Router。
- `interface.json`：公共工具、契约和实际文件依赖。
- `requirements.json`：逐条 claims、实现、测试、未解决能力。
- `tests/manifest.json`：covers / exercises / depends_on_artifacts。
- `changes/`：验收工具生成的版本记录；与具体资产的人工批准无关。

```powershell
.\scripts\govern.ps1 validate
.\scripts\govern.ps1 graph --mermaid
.\scripts\govern.ps1 impact --from runtime.asset_router
.\scripts\govern.ps1 contract-test
.\scripts\govern.ps1 test --requirement REQ-GOV-001
```

当前本机默认使用 `D:/contract-govern skill` 的工具环境，可通过 `CONTRACT_GOVERN_HOME` 配置。
只对源码副本做治理检查，实际项目资产与依赖缓存不进入 Skill 版本。详见 [迁移与证据范围](docs/governance/MIGRATION.md)。

## 已实现

- 项目 Manifest、七类 JSON Schema、显式状态机、原子写入、独占写锁与版本检查。
- `plan_only`、`stage1_only`、`stage2_only`、`full_pipeline`、资产级 `repair`。
- 本地资产库适配器、检索记录、许可证门禁、A/B/C 路由。
- Stage 1 原始资产/输出版本隔离、文件校验、来源与生成配方记录、人工审核、有限返工。
- 本地/远程 HTTPS/SSH HY3D 网关客户端，SSH 环境检查、能力与健康检查；B1 重贴图与 C 生成入口。
- 默认 Blender MCP：预检、可审阅操作步骤、实际输出回收；另保留显式选择的 batch 后端。
- Blender 工作者：GLB/OBJ 导入、集合组织、底部居中、摆放、箱体/轨道几何、材质、摄影机、太阳光、预览与 BLEND/GLB 导出；在新场景构建，保留原有场景。
- 资产打包、场景最终审核及交付，保留来源、归属声明、Manifest 快照和校验和。

`init --brief` 保存需求，不会自动调用语言模型。Codex 依据 `prompts/` 完成需求优化、分解和美术决策，再交给运行时执行。示例样式是可编辑的起点，不代表对用户意图的自动推断。

## 安装与测试

本地运行时要求 Python 3.11+；正式场景构建需运行中的 Blender MCP 插件服务，工作者面向 Blender 4.2+。HY3D 的远程环境独立配置，不需要在本机安装 GPU 推理依赖。在项目根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
python -m pytest -q
python -m runtime.cli --help
```

本次开发环境没有系统 `python` 命令，依赖已放在项目 `.deps/`。
可直接使用本机启动脚本，脚本优先寻找项目虚拟环境或系统 Python，随后寻找 Codex 附带的 Python：

```powershell
.\scripts\two-stage-3d.ps1 --help
.\scripts\test.ps1
```

依赖范围由 `pyproject.toml` 管理，本次测试所用版本记录在 `requirements-tested.txt`。

首次使用先复制 `.env.example` 为 `.env`，再在 `.env` 内填写实际部署值。CLI 读取 YAML 时会加载根目录 `.env` 并解析 `${NAME}`；调用进程已经设置的环境变量优先于文件值。缺少被引用的变量会在连接或推理开始前报错。`.env` 已加入 `.gitignore`，不要把真实值复制回 YAML、文档或 `.env.example`。

## 本地完整资产流程

仓库自带原创 CC0 简模长椅。以下命令实际复制资产，不调用网络或 HY3D。

```powershell
.\scripts\two-stage-3d.ps1 init projects/my_station --id my_station --brief '安静的乡间车站，长椅与轨道' --mode full_pipeline --task templates/asset_task.yaml
.\scripts\two-stage-3d.ps1 status projects/my_station
.\scripts\two-stage-3d.ps1 approve-plan projects/my_station
.\scripts\two-stage-3d.ps1 stage1 projects/my_station --asset-id bench --catalog examples/library/catalog.yaml
```

此时资产为 `review_required`，结果记录位于 `stage1/results/bench_rev00.json`。
检查实际模型与来源后执行以下审核操作：

```powershell
.\scripts\two-stage-3d.ps1 review projects/my_station bench --decision approved
Copy-Item templates/blender_plan.yaml projects/my_station/stage2/blender_plan.yaml
.\scripts\two-stage-3d.ps1 stage2 projects/my_station --dry-run
```

`--dry-run` 仅校验输入，不调用 Blender、不创建模型，也不改变构建状态。
默认通过 Codex MCP 执行，不需要填写 Blender 可执行文件路径：

```powershell
.\scripts\two-stage-3d.ps1 stage2 projects/my_station
```

该命令生成 `stage2/scene/mcp-*/mcp_calls.json`，由 Codex 顺序调用 Blender MCP 执行加载、组装、导出和渲染步骤。CLI 不会伪装成可直接调用 Codex 的会话工具。渲染步骤异步排队；超时后检查状态，不要重复提交。

实际文件生成后，使用返回的 build_id 登记构建结果：

```powershell
.\scripts\two-stage-3d.ps1 stage2-complete projects/my_station --build-id mcp-返回的12位编号
```

检查 `stage2/scene/mcp-*/preview.png` 和场景文件后，进行最终审核与交付：

```powershell
.\scripts\two-stage-3d.ps1 approve-final projects/my_station
.\scripts\two-stage-3d.ps1 deliver projects/my_station
```

仅在明确需要独立后台 Blender 时选择 `--backend batch --blender <实际可执行文件路径>`。

资产、样式、场景计划或输出内容在构建后发生变化，会阻止最终审核或场景交付。
只需要资产库时，将交付目标设为 `asset`，可在 Stage 1 审核后直接打包：

```powershell
.\scripts\two-stage-3d.ps1 configure projects/my_station --target asset
.\scripts\two-stage-3d.ps1 deliver projects/my_station
```

## 其他模式

`run <project> --catalog <catalog>` 按保存的模式继续：`plan_only` 只展示计划；Stage 1 执行后在必要审核处停下；`full_pipeline` 在输入已获批后准备 MCP 步骤。它不自动批准最终场景，也不会自动重跑失败任务。`stage1 --asset-id` 用于显式执行或重试单项任务。

返工示例（只产生 bench 的新版本，保留原始源文件和其他资产）：

```powershell
.\scripts\two-stage-3d.ps1 configure projects/my_station --mode repair
.\scripts\two-stage-3d.ps1 review projects/my_station bench --decision revision_requested --instruction '简化木纹，保留现有轮廓'
.\scripts\two-stage-3d.ps1 stage1 projects/my_station --asset-id bench --catalog examples/library/catalog.yaml --hy3d-config configs/hy3d_ssh.yaml
```

路由重新按任务约束与候选评分评估。若要强制重贴图，应在初始任务中选择 `library_hy3d_refine`；MVP 尚无交互式任务编辑命令。不要把直接复制资产当成已经满足了返工要求，必须再次审核。每项任务默认最多 3 次新版本，不自动增加限额。

`stage2_only` 不执行检索。先用 `init --mode stage2_only` 创建项目，再用 `supply <project> <asset_id> <model> --source <source.yaml>` 导入文件及已核实的来源信息，提供包含该 ID 的 Blender 计划并批准计划。来源字段见候选目录里的 `source`。

自动批准资产需明确设置 `configure --auto-approve`；恢复人工审核用 `--no-auto-approve`。
允许缺少部分必需资产需明确设置 `--allow-partial`，并从 Blender 计划中省略它们。计划里列出的资产仍必须存在且获批。占位几何可显式写为 procedural box。

## 接口和边界

- [Skill 入口](SKILL.md)、[父编排提示](prompts/parent.md)、[规划提示](prompts/asset_planner.md)。
- [HY3D 网关协议](docs/hy3d_gateway.md)：这是本项目协议，需要匹配的服务适配层；没有假定原生 HY3D 服务接口。
- [资产模板](templates/asset_task.yaml)、[Blender 计划模板](templates/blender_plan.yaml)、[来源样例](examples/library/catalog.yaml)。
- 目前支持嵌入资源的 GLB 和不引用 MTL 的纯几何 OBJ。FBX、GLTF 多文件包、BLEND 导入暂不支持。
- 本地目录中的评分和许可证由维护者提供，运行时不自动推断质量或解读许可证。当前接受已核实的 `cc0`、`cc_by`；未知许可会被阻止。
- 路径规则、状态机与角色权限是应用层约束。Python 对象和提示词不能替代操作系统权限；真正的受限多进程 Worker 需要宿主提供独立目录和工具权限。当前执行器是顺序执行。
- `.manifest.lock` 使用独占创建；进程崩溃后需确认无写入进程，再手动移除遗留锁。不会擅自抢锁。
- 不在 Manifest 中存储密钥。HY3D 密钥通过环境变量提供。不要将配置、提示或生成配方中的任意文本当作可执行代码。

## 尚未完成及验证范围

Phase 2/3 后续项：Sketchfab/Poly Haven 等远程资产库、受限并行 Worker、自动视觉评分、B2/B3 细化策略、丰富的程序化几何、缓存/检索数据库、Dashboard 与 Web 导出/部署。选择 `web` 会明确报未支持，不会自动发布。

首版 Blender 工作者不实现自动拓扑修复、法线修复、复杂材质统一或自动尺寸推断；保留导入材质，利用计划中的缩放设置尺寸。技术校验是容器与依赖路径检查，不等同于完整 glTF 校验或美术验收。

自动测试覆盖真实文件流、本地测试 HTTP 网关、MCP 操作顺序/撤销审核拦截/输出回收和 SSH 参数/隧道清理。MCP 与 SSH 进程边界使用测试替身。已发现 Codex 的 Blender MCP 工具，但最近连接检查提示插件服务不可达；远程服务器尚未准备。真实 SSH 连接、推理、渲染及 Blender 版本兼容性尚未实测。示例项目不宣称是已完成的 3D 场景。
