# Two-Stage 3D

将文字需求与参考图制作成可审核、可修改、保留来源的静态 3D 场景。
由 Codex 编排，Python 管理资产与制作状态，Blender 完成几何、材质、灯光、相机和渲染。

适合环境场景、建筑与车站原型、工业道具，以及已有资产的统一风格组装。
交付内容包括 Blender 场景、实际预览 PNG、资产来源、制作记录和文件校验清单。
Skill 调用名为 `two-stage-3d`，入口是 [SKILL.md](SKILL.md)。

## 工作流程

| 阶段 | 工作 | 产物 |
| --- | --- | --- |
| 视觉规划 | 理解需求、参考用途、对象与风格，交由用户审核 | 视觉简报、参考板、场景规格、风格选择 |
| 几何获取 | 先搜索配置的资产库，再选用现有模型、明确缩放、生成或程序化构件 | 模型、来源与几何审核记录 |
| 场景制作 | 组合获批几何，配置语义材质，编译相机与灯光方向，通过 Blender 执行 | 布局、外观与渲染计划、BLEND、预览 PNG |
| 画面复审 | 查看实际图片，在允许范围内修订，保留每轮历史 | 视觉评论、修订记录、最终审核与本地交付包 |

支持外部 `render-director` 提供画面方向：本项目输出 RenderContext，接收并校验
RenderDirection，将相对相机/灯光关系编译为可执行计划。实际 PNG 完成后，再由
Render Director review/refine 提出下一轮方向。生产端保留审核、版本与执行边界。
安装外部 Skill 后由宿主调用其公开入口，详见 [接入说明](docs/v02/render-director.md)。

默认只规划。视觉方案、几何与最终画面分别审核；通过文件检查、生成操作包或排队渲染
不等于用户批准，也不等于真实输出已经完成。

## 开始使用

需要 Python 3.11+；实际场景执行需要 Blender 4.2+ 与宿主配置的 Blender MCP。
请在项目专用 Conda 环境中安装依赖，不向系统 Python 或 base 安装。

```text
python -m pip install -e .
python -m runtime.cli doctor
```

`doctor` 检查本机软件发现结果；服务是否在线仍需当前会话验证。
安装整个目录，保留代码、Schema、风格资源、提示词、模板和指南，不能只复制 SKILL.md。
平台路径与 MCP 配置见 [平台说明](docs/platforms.md) 和 [连接说明](docs/mcp_and_ssh.md)。

以下例子只生成待审核方案，不需要 Blender 或远程模型在线；项目目录应尚不存在。

<!-- executable: readme-visual-start -->
```text
python -m runtime.cli init-v02 projects/v02_demo --id v02_demo --brief "Quiet industrial station with matte teal equipment and warm concrete"
python -m runtime.cli reference-add-v02 projects/v02_demo examples/v02/reference.svg --id ref_material --role material_language --source examples/v02/reference_source.yaml
python -m runtime.cli stage0-submit projects/v02_demo --proposal templates/v02_stage0.yaml --expected-version 0
python -m runtime.cli status projects/v02_demo
```

结果应为 `plan_only / visual_review_required`，等待用户审核。完整操作见
[快速入门](docs/v02/quickstart.md)、[几何获取](docs/v02/geometry.md)、
[场景制作](docs/v02/production.md)、[预览](docs/v02/preview.md)、
[画面复审](docs/v02/visual-review.md) 和 [交付](docs/v02/delivery.md)。

## 风格与资产

内置工业风格提供可执行材质、灯光、相机和颜色管理配置；也可导入用户自己的风格包，
选择明确的风格 ID 与版本。`execution_default` 保存执行默认值，`direction_prior`
只向外部视觉导演提供倾向。风格包的检查、校准与导入见 [用户风格](docs/v02/user-styles.md)。

本地资产支持嵌入资源的 GLB 和纯几何 OBJ。程序化构件包括地面、墙、平台、柱、栏杆和管道。
可选 Hunyuan3D 后端提供几何及原始表面来源，最终外观由场景材质流程确定。
模型服务、权重、凭据及用户素材需自行配置，不包含在 Skill 中。

## 使用边界

- 面向静态场景；不包含角色绑定、动画、训练、游戏引擎集成或在线发布。
- 每个语义对象支持一个 body 材质槽；不同部件的材质应拆分对象。
- 视觉修订保留获批几何，受当前评论、保留字段和预览次数限制；更换几何需另行审核。
- 交付已完成的预览与场景；没有独立高质量 final-render 或当前场景流程的 GLB 导出入口。
- 默认使用 Blender MCP；连接失败不自动切换执行方式。迁移机器后重新生成操作包。
- 真实 GPU 生成、画面质量和外部视觉判断需要针对当前输入验证，不能由接口测试代替。

旧 Schema 0.1 资产项目仍可按 [资产工作流](docs/workflow.md) 使用，迁移工具只生成候选方案，
不会自动改写旧项目或转移批准。
