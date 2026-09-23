> Compatibility reference for existing legacy directed projects. Current visual production uses [visual tasks](task-tracking.md); optional implementation details are in the [internal adapter guide](visual-task-adapters.md). The historical requirements and examples below apply only to that legacy path.

# Render Director 接入

本 Skill 负责场景数据、执行计划、Blender 操作、版本、来源与审核。
外部 `render-director` 负责当前画面的相机、构图、灯光、氛围与视觉评论。
使用宿主可用的该 Skill 的 `analyze`、`review`、`refine` 入口；它不是本项目
虚构的 CLI 或自动后台服务。未安装时报告依赖缺失，保留当前项目等待接入；
用户明确选择直接编写计划时，可以继续使用原有执行默认值。

## 输入与数据边界

Stage 0 保存视觉目标、主次对象、必需元素、避免事项、参考用途与精确风格版本。
`visual_brief.constraints` 可附加 `user_constraints` 和 `preserve`。
不在 Stage 0 确定相机 XYZ 或灯光坐标。

Stage 1 完成并获批后，用 Blender 当前几何和布局测得各语义对象的世界空间包围盒。
测量须包含父级变换、旋转、缩放及重复实例。在 Blender MCP 中调用
`runtime.blender_geometry_worker.measure_scene_bounds(project_root, approved_geometry, blockout_plan)`
可在临时场景中导入、放置并测量，结束后恢复原场景。`world_bounds` 也可读取已有已放置对象；
`build_scene_context(manifest, scene_spec, bounds_by_object,
blockout_plan=..., ground_z=..., environment_summary=..., scene_type=...)` 聚合这些数据。
上下文绑定实测时的几何与布局摘要；布局改变后必须重新测量，不能复用旧包围盒。
未知包围盒须先测量，不能将 scene_spec 的目标尺寸当成实测值。

公开场景类别为 `hero_prop`、`industrial_environment`、`industrial_megastructure`、
`interior`。已有 `industrial_station` 明确映射到 `industrial_environment`；其他未知类别
需显式指定上述类型。私有 SceneContext 仍保留主体包围盒、地面高度和几何摘要。

```text
python -m runtime.cli render-context PROJECT --scene-context SCENE_CONTEXT.json
```

将标准输出作为 RenderContext 交给 `render-director analyze`。对方的公开 1.0
接口不接受任意扩展键，因此 Stage 0 目标/必需元素/避免事项放在标记清楚的
`intent.user_constraints` 文本中；主体包围盒、地面、风格先验和同场景历史观察
以标记清楚的 JSON 文本进入 `scene.environment_summary`。参考来源元数据进入
`references.description`。主体 ID、场景总包围盒、风格 ID/版本和参考用途保持结构化。
`material_language` 映射为 `material_readability`；几何/色板参考保留原用途说明，
以公开的 `style` 角色传入。该映射不改变参考授权。

## 编译与执行

保留原有 blockout_plan 和 semantic_material_map。返回的 RenderDirection 必须通过
公开 Schema、项目/场景身份和用户保留字段检查，才能编译并提交：

```text
python -m runtime.cli scene-plans-submit PROJECT --plans PLANS.json --render-direction DIRECTION.json --scene-context SCENE_CONTEXT.json --expected-version N
```

PLANS 包含四份计划的身份与目标输出信息；适配器替换 lookdev/render 的视觉执行字段。
相机按主体包围盒八个顶点、水平 sensor、输出纵横比、焦距、目标占比和目标偏移
求透视距离，写入世界位置、目标、旋转与裁剪范围。相机低于场景地面时拒绝，
由外部导演修订方向，不自动改变视角。

camera_subject 灯光方位的零度指向主体到相机的方向；正角绕世界 Z 轴逆时针。
灯光类型、能量、颜色、环境与资源来自 Style 的 execution_default，当前方向
提供相对角度、柔度和补光比。当前执行器支持 AREA 灯光。方向中的 `moderate/heavy`
雾量映射为生产计划的 `medium/dense`。曝光 intent 属于语义提示，1.0 接口没有数值
EV；执行仍使用 Style 曝光默认值，不猜测调整量。构图与材质可读性说明保留为
外部审图依据，不自动移动或修改获批几何。

随后照常执行 `scene-prepare`、Blender MCP 操作、`scene-setup-complete` 和预览流程。
准备计划不代表已生成图片。改变相机/灯光后仍须核对几何指纹。

## 实际 PNG、复审与修订

```text
python -m runtime.cli render-context PROJECT --scene-context SCENE_CONTEXT.json --review
```

只有已完成、摘要匹配的当前 PNG 才能进入复审。将此 RenderContext、当前
RenderDirection 和实际 PNG 交给 `render-director review`。查看真实图片后，
将其诊断整理为现有九类 visual_review，并将两份报告一起提交：

```text
python -m runtime.cli visual-review-submit PROJECT --review VISUAL_REVIEW.json --director-review RENDER_REVIEW.json --expected-version N
```

RenderReview 不能作为执行计划。需要返工时，把上下文、前一方向和该报告交给
`render-director refine`，获得同一 ID、revision + 1 的新方向。提交新方向与原有
revision_plan，由生产门禁检查后再执行：

```text
python -m runtime.cli revision-apply PROJECT --revision REVISION_PLAN.json --render-direction REVISED_DIRECTION.json --expected-version N
```

检查当前图片、方向版本、推荐字段、改变清单和 preserve。小/中修订上限分别为
相机角度 5/10 度、焦距 5/10 mm、画面占比 0.05/0.1、灯光角度 5/10 度、补光比
0.1/0.2、雾量 1/2 档。超限或未实现的语义修改需重新规划与审核，不会静默执行。
初始方向若要求保留尚不存在的镜头，须先明确基准。最多三次预览尝试，包含失败。
几何审核、用户批准和材质映射均不会由 Render Director 修改。

`.render_direction/history/` 保存不可变方向、输入上下文与 SceneContext，`reviews/`
保存关联实际 PNG 的报告。Manifest 只记录当前引用、摘要及历史引用；以该引用
解析当前方向，不依赖可被覆盖的 current_direction 缓存。观察从已验证的同场景
报告重建，后续修订自动读取；它们随交付保存，不回写共享 Style。

## 风格配置

组件中的 `execution_default` 是可执行默认值；旧版平铺参数作为兼容默认值。
`direction_prior` 是外部导演参考的倾向，不能覆盖执行参数。相机组件例如：

```yaml
profile: environment
execution_default:
  focal_length_mm: 48
  clip_start: 0.1
  clip_end: 500
direction_prior:
  focal_length:
    preferred: [32, 50]
    allowed: [24, 70]
```
