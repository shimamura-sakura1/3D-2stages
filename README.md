# Two-Stage 3D — 精简运行分发

这是当前 **S17** 的运行文件分发。生产代码、SKILL 编排、契约和风格资源均与维护工作区逐字节一致。
S17 是工作版本，最后正式接受版本为 **S13**；本次发布不等于补做正式验收。

## 使用

在独立 Python 3.11+ 环境安装本目录，然后让 Codex 从 [SKILL.md](SKILL.md) 进入。

```text
python -m pip install -e .
python -m runtime.cli --help
```

从 [v0.2 离线快速入门](docs/v02/quickstart.md) 创建视觉项目。实际 Blender 操作默认经 MCP，最低 Blender 4.2，验证基线为 4.5.13 LTS。
远程 HY3D 设置见 [连接说明](docs/mcp_and_ssh.md)，真实主机及凭据填写到被 Git 忽略的 `.env`。
完整执行边界见 [生产](docs/v02/production.md)、[预览](docs/v02/preview.md)、[返工](docs/v02/controlled-revision.md)、[最终审核与交付](docs/v02/delivery.md)。

## 当前范围

包含 Stage 0 视觉规划、资产库优先的几何获取、程序化几何、语义材质与风格配置、Blender 预览、独立视觉评论、受限返工以及绑定明确用户批准的本地交付。
默认 plan_only；技术检查不会授予美术批准。v0.1 兼容入口继续保留。

源版本已通过 34 组活动回归及治理契约检查，并完成真实 MCP 两轮预览、修订、交付和 BLEND 重载验证。
集成测试中的用户审核为明确标注的模拟决定，不能替代正式车站的最终美术批准。
HY3D 实际推理和原始/风格化比较仍因显存不足暂停，标准混合来源场景最终验收未完成。

迁移目前只生成只读草案；每个语义对象支持一个 body 材质槽，复合材质需拆分对象。
HY3D Paint 可保留原始表面证据，尚不支持最终材质混合。当前交付已有预览和 setup BLEND，不另行执行高质量 final-render 或 Web 发布。

## 分发与维护

本分支只供运行，省略 tests、changes、治理缓存、阶段实施报告、真实项目和凭据。
所需生产指南、接口/需求元数据、配置模板、原创最小示例及 Blender 风格库保留。
维护协议仍适用：修改能力前需使用保留完整测试与 changes 历史的维护 checkout，并依照 [维护步骤](docs/governance/EVOLVE.md) 执行；本运行分支不具备独立治理验收所需历史。

[RELEASE.json](RELEASE.json) 记录版本与源文件摘要，[FILES.sha256](FILES.sha256) 校验发布文件。
本地完整维护工作区未删除，原仓库 main 分支未被覆盖。
