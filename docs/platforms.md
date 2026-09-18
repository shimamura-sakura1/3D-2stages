# macOS / Windows 运行约定

两平台使用同一套 Python CLI、Schema 和审批状态机；自动适配只处理操作系统路径、已安装 Blender 的发现，不代替软件安装、MCP 配置或远程服务授权。

## 环境与启动

Python 要求 3.11+。为项目创建独立 Conda 环境；为 MCP 等不同依赖集合另建独立环境。创建前检查同名环境是否已存在，不向 base、系统 Python 或其他项目环境安装包。

激活项目环境并进入仓库后，以下命令在 macOS 的 shell 和 Windows PowerShell 中相同：

```text
python -m runtime.cli doctor
python -m runtime.cli --help
```

`doctor` 只报告当前平台、实际 Python、Blender 可执行文件发现结果，不启动服务，不证明 Blender 版本/MCP 连通或 HY3D 就绪。任一依赖缺失会在相应字段中明确标注，不妨碍只做规划或 Stage 1 本地资产工作。

Windows 的 `.ps1` 文件是可选帮助脚本，不是 macOS 启动入口。两平台优先用激活后环境中的 `python -m runtime.cli`。复制模板时 macOS 用 `cp`，Windows 用 `Copy-Item`；文件路径含空格时作为一个带引号的参数传入。

## Blender 与 MCP

- Stage 2 最低 Blender **4.2**，固定工作者在修改场景前检查版本。4.5 LTS 是当前部署基线，其他满足下限的版本仍需实际兼容性验证。
- Blender 桌面程序及其自带 Python 与项目/MCP Conda 环境分开；远程 HY3D 的 `bpy 4.0` 不是桌面 Blender 的版本要求。
- 默认 MCP，由当前宿主配置的工具检查插件状态并执行操作包。每台机器均需安装插件和注册 MCP；Skill 不能预先声称所有会话都有这些工具。MCP 使用本机专用解释器的绝对路径，不能照抄另一平台的路径。
- 明确选择 `--backend batch` 时，按 **`--blender` → `BLENDER_EXECUTABLE` → PATH → 本机常规安装目录** 发现可执行文件。显式配置错误会拒绝执行，不静默改用另一安装。macOS 搜索系统/用户 Applications 的 Blender.app；Windows 搜索 Program Files / LocalAppData 中 Blender Foundation 的安装目录，版本目录按数字排序。便携版或自定义目录用显式配置。
- `BLENDER_EXECUTABLE` 可设为进程变量或本机忽略的 `.env` 值；运行时读取项目文件时解析 `.env`，已有进程变量优先。
- 自动发现不自动切换 MCP/batch，不安装 Blender，也不将文件初检当作美术验收。

## 项目搬迁

公开 Stage 0 模板中的参考 SVG 按原始字节 SHA256 命名；仓库通过 `.gitattributes` 固定该示例为 LF，因此 macOS 与 `core.autocrlf=true` 的 Windows checkout 使用同一摘要。正式交付包继续使用项目相对路径和内容摘要；Windows 的物理文件读写可处理深层目录产生的长路径，macOS 保持原有路径行为。

Manifest、任务、资产结果与 Blender 计划中使用项目相对路径，输出统一写 `/`。读取相对路径时接受 `/` 或 `\`；无论宿主系统，都拒绝 Windows 盘符、UNC、根路径、POSIX 绝对路径及 `..` 路径逃逸。

`request.json`、`ticket.json` 和 `mcp_calls.json` 包含执行机器的绝对路径和摘要。迁移到另一系统后重新生成操作包，不能复用旧操作包直接执行。现有资产审核仍须检查文件与版本有效性；机器路径、SSH 密钥路径和 MCP 解释器配置各机独立。
