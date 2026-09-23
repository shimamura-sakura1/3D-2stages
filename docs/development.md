# 在另一台电脑继续开发

`dev/v3` 保存完整源码、测试、开发文档和历史记录；`main` 是给使用者安装的 Skill。开发完成后通过导出脚本发布到 `main`，不把整个开发分支合并进去。

## 获取完整源码与依赖

先安装 Git、Git LFS、Conda。以下命令可在 PowerShell 或 macOS 终端执行。已有专用环境可以继续使用；不要向 base 或系统 Python 安装依赖。

```sh
git clone --branch dev/v3 https://github.com/shimamura-sakura1/3D-2stages.git
cd 3D-2stages
git lfs install --local
git lfs pull
conda create -n two-stage-3d-dev python=3.12
conda activate two-stage-3d-dev
python -m pip install -e ".[dev]"
```

历史验收记录通过 Git LFS 保存，必须拉取实际内容；不要把 LFS 指针文件当作 JSON 记录。`requirements-tested.txt` 是历史测试环境记录，当前项目依赖入口为 `pyproject.toml`。

在本项目同级获取维护框架：

```sh
git clone https://github.com/shimamura-sakura1/contract-govern-skil.git ../contract-govern-skil
git -C ../contract-govern-skil checkout d6996c6201c2ad9b364add42363b05c70cb42d62
```

基础开发和 main 的视觉生产不要求安装其他视觉 Skill 或知识库。可选实现的当前文件任务协议会检查十份公开 Schema、实际入口和解释器依赖；不可用时走 main，显式指定时才作为缺口报告。旧的三 Schema 检查仅诊断历史协议，不能作为新协议就绪依据。按需配置见 [内部适配](v02/visual-task-adapters.md)，不再默认要求固定旧提交。

## 配置这台机器

Blender 最低 4.2。安装 Blender 和 Blender MCP，MCP 的 Python 依赖使用另一个专用环境；在当前宿主中注册 MCP 服务。不要复制另一台机器的 Codex 配置、解释器路径或凭据。本项目不会自动覆盖宿主 MCP 设置，也不会因连接失败切换 batch。

先做只读检查：

```sh
python scripts/setup_dev.py
```

然后把以下 `BLENDER_PATH` 换成这台机器的可执行文件路径，写入本地配置：

```sh
python scripts/setup_dev.py --blender "BLENDER_PATH" --framework ../contract-govern-skil --write-local
python scripts/setup_dev.py
python -m runtime.cli doctor
```

Windows 路径指向 `blender.exe`；macOS 指向应用包内的 `Contents/MacOS/Blender`。检查会实际执行 `--version`，不会创建场景或渲染。退出码 0 表示开发文件与依赖检查通过，1 表示仍有缺失或不兼容项目，2 表示参数或配置错误。

`--write-local` 只写被忽略的 `.deps/development-host.json` 和 `.env`；已有服务凭据和无关配置保留。后续 `setup_dev.py` 会读取保存的路径。框架维护命令仍使用明确的 `--framework`，或由你设置进程变量 `CONTRACT_GOVERN_HOME`。

安装路径正确和 MCP 连接成功是两件事。让当前 Agent 调用 `get_addon_status`、`get_scene_info`，确认真实插件握手和场景可读。只有桥接进程在列表中显示连接，不能证明 Blender 已启动。状态工具异常时继续检查场景读取、Blender 进程、实际配置端口，保留具体错误。

本机可另外配置启动助手，在没有 Blender 实例时启动软件、已有实例时复用；这属于各机宿主设置。不得把某台机器的启动器绝对路径写进共享 Skill，也不得为检查而关闭已有场景。

## 日常开发与验证

从 `dev/v3` 开始，提交和推送后再换机器；另一台机器先拉取最新 `dev/v3` 与 LFS 对象。不要跨电脑复制 `.venv`、Conda 环境或 `.deps` 整个目录。

修改 Skill 前遵循 [维护流程](governance/EVOLVE.md)，保留旧 requirements、tests 和 changes。示例：

```sh
python scripts/govern.py --framework ../contract-govern-skil validate
python -m pytest -q tests/test_developer_setup.py tests/test_release_preparation.py tests/test_production_distribution.py
```

阶段开发只跑新增和相关测试，保存首次失败、影响分析、最终结果和实际 I/O。正式验收按本次授权通过 `scripts/govern.py accept` 执行校验、契约测试和全部 active 历史测试，避免事先无必要地再跑一遍全量。S26—S30 是开发阶段标识；只有工具生成成功记录才是 accepted。未完成真实验证的能力继续 unresolved。

`projects/`、参考图、私人资产库和本机诊断通常被忽略，不随代码克隆。需要继续某个建模项目时另行传递它的项目目录及依赖资产，保留相对层级；服务凭据单独配置。迁机后重新生成 MCP 操作包，不执行旧包里的绝对路径。

## 发布到 main

先提交并推送开发变更，确保 `dev/v3` 的受跟踪文件干净。创建单独的 main 工作目录：

```sh
git fetch origin
git worktree add ../two-stage-3d-main main
git -C ../two-stage-3d-main pull --ff-only origin main
python scripts/prepare_release.py --target ../two-stage-3d-main
git -C ../two-stage-3d-main diff --stat
git -C ../two-stage-3d-main add -A
git -C ../two-stage-3d-main commit -m "Publish Skill from dev/v3 SOURCE_COMMIT"
git -C ../two-stage-3d-main push origin main
```

如果本地还没有 `main`，先用 `git branch --track main origin/main` 建立跟踪分支。把提交说明中的 `SOURCE_COMMIT` 换成导出报告里的完整开发提交，保留发行来源。每台机器用自己的工作目录，不复用上面的路径名称作为硬编码。

`prepare_release.py` 会检查源分支是 `dev/v3`、目标是同一仓库的 `main` 工作目录、两边没有未提交的受跟踪改动；只导出允许的已跟踪文件。它会在目标中移除旧发行文件、写入新发行内容，但不会提交、推送、修改源工作区或删除私人项目。`main` 不包含开发文档、测试、维护框架和本机配置。

旧分支由 `archive/2026-09-19/...` 标签保存迁移前位置。日常仅使用 `dev/v3` 和 `main`。
