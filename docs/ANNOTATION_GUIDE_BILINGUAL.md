# 每张图片的标注指导 / Per-image Annotation Guide

这份清单给实际标注和复核人员使用。标注器右侧的 **逐图指导 / Image Guide** 会根据当前图片进度提示下一步；下面是完整规则。

This checklist is for annotators and reviewers. The **逐图指导 / Image Guide** tab on the right changes with the current image and points to the next action. The full rules are below.

## 中文：每张图都按这 4 步做

### 第 1 步：先看纯净 RGB

1. 点 **纯净 RGB**（快捷键 `` ` ``），先看整张原图。
2. 检查图片是否损坏、严重缺图，或大面积被水面等无关区域占据。
3. 先找主路，再找清晰的人行道、园路、支路和后勤道路。
4. 不要只盯着已有草稿；草稿可能错位、漏路，也可能包含不属于任务的路线。

### 第 2 步：画对完整路线

按 `P` 画路线，按 `V` 选择和修正控制点。**标注的是稳定可导航通道的标准中心线，而不是某次机器人实际轨迹。** 每条线表示一条可复现的固定 corridor。

- 单一人行道、园路或窄巷：沿可通行 corridor 的视觉中心附近画，不跟随某个人可能走过的偏线。
- 无实体分隔的普通窄道路：整个道路是一个连续 corridor 时只画一条 canonical centerline，不要随意画两条平行线。
- 有中央隔离带、绿化带或护栏的双向道路：视为两个独立 corridor，两侧各画一条，绝不能画在中间分隔线上；只在真实路口、开口或斑马线连接。
- 宽广且没有稳定主轴的广场、开放铺装区或停车区域：不要凭感觉画一条“机器人可能走”的线，只标明确 walkway/corridor。
- 清晰可见的小路、园路、连接支路要补齐。
- 道路边界、草坪边缘、建筑轮廓不是路径，不要沿边画。
- 路线到图片边缘时应停在边界内，不能伸出 RGB 图片。
- 树冠、阴影或建筑遮挡处只能画你能够合理确认的 geometry；不要为了让路网“看起来完整”凭空补路。

画线时单击增加控制点，双击或 `Enter` 完成，`Backspace` 撤回本次最后一点，`Esc` 取消。

### 第 3 步：逐段审核 Evidence

按 `X`，有两种方式选区间：按住沿路线拖动，或先点起点、再点同一路线上的终点，然后按对应字母。单击只设置起点，不会自动生成一小段：

| 键 | 类别 | 什么时候用 |
|---|---|---|
| A | 清晰可见 | RGB 中能直接、清楚地看到路线 |
| B | 弱视觉证据 | 有树荫、阴影或低对比，但仍能指出具体支持像素；可在属性中选视觉困难原因 |
| C | 仅语境推断 | RGB 很难确认，主要靠入口、出口或布局推断 |
| D | 草稿错位 | 自动草稿明显偏离可见路线；先标问题，再修 geometry |
| E | 不属于任务 | 该要素可能存在，但不属于机器人目标路径网络 |
| U | 不确定 | 当前无法可靠判断，留给复核人员 |

最重要的区分：**B = Weak Visual 仍必须能指出具体 RGB 视觉证据。** 如果主要依赖布局或生活常识判断路径存在，应标 C = Context Only。低分辨率不自动等于 B；图太糊而只能猜测时，应标 C。

Evidence mode 中的 **E 是局部 Task Mismatch**：局部 E 只排除选中区间；只有右键或属性中的 **排除整条路径 / Exclude Entire Path** 才排除整个 polyline。整路排除后路线会变成灰色，仍可使用 **恢复整条路径 / Restore Entire Path**，并支持撤销/重做。

颜色提示：琥珀色虚线 = 未审核；绿色 = A 清晰可见；橙色 = B 弱视觉证据；紫色 = C 仅语境推断；红色 = D 草稿错位；灰色 = E 任务外；蓝灰色 = U 不确定。

若 B 的证据较弱，可在属性面板选择 `tree_canopy`、`shadow`、`low_contrast`、`low_resolution`、`narrow_structure`、`building_occlusion`、`mixed` 或 `other`。该字段可留空；把 B 改成其他类别时会自动清除。

### 第 4 步：保存前检查

每张图切到下一张之前，逐项确认：

- [ ] 清晰的主路、小路、人行道、园路和支路没有漏标；
- [ ] 线位于稳定可导航通道的标准中心线上，而不是某次机器人轨迹；
- [ ] 双向道路没有画在中央隔离带或双黄线上；
- [ ] 没有路线伸出图片范围；
- [ ] 所有路线区间都有 A/B/C/D/E/U；
- [ ] D 段修正 geometry 后，已经重新标为 A/B/C/U；
- [ ] 看不清的部分没有被当成可靠 A；
- [ ] 空图确实没有目标路线后，才点“确认本图已审核”。

最后点 **保存并下一张**，或按 `Ctrl/Cmd + Enter`。程序只写 JSON，不改原始 RGB。

## English: follow these four steps on every image

### Step 1: inspect Clean RGB

1. Click **Clean RGB** (shortcut: `` ` ``) and inspect the full image.
2. Check for corruption, missing imagery, or a large irrelevant water area.
3. Find major roads first, then visible sidewalks, garden paths, side paths, and service roads.
4. Do not rely only on the draft. A draft may be shifted, incomplete, or outside the task.

### Step 2: draw complete paths in the right place

Press `P` to draw and `V` to select or edit control points. **Annotate the canonical centerline of a stable navigable corridor, not an arbitrary robot trajectory.** Each polyline is a reproducible fixed corridor.

- For a sidewalk, garden path, or narrow lane, draw near the visual center of the usable corridor.
- For an undivided narrow road that is one continuous corridor, draw one canonical centerline, not two arbitrary parallel lines.
- For a divided road, draw each usable side separately. Never draw on the center separator, median, or double yellow line; connect sides only at real openings, junctions, or crossings.
- For a very wide open area without a stable travel axis, do not invent a polyline. Annotate only explicit walkways/corridors.
- Add visible small paths, garden paths, connectors, and side roads.
- Road boundaries, lawn edges, and building outlines are not paths.
- Stop geometry inside the image boundary; never extend a path outside the RGB.
- Under canopy, shadow, or building occlusion, draw only geometry you can reasonably support. Do not invent continuity to make the network look complete.

Click to add points, double-click or press `Enter` to finish, press `Backspace` to remove the last new point, or `Esc` to cancel.

### Step 3: review evidence span by span

Press `X`. Select a span by dragging along one route, or click its start and then its end (the latter is easier on a trackpad), then press a class key. A single click only sets the start; it does not create a tiny automatic span:

| Key | Class | Use when |
|---|---|---|
| A | Clear Visual | The path is directly and clearly visible in RGB |
| B | Weak Visual | Canopy, shadow, or low contrast interferes, but specific supporting pixels remain |
| C | Context Only | RGB alone is weak; the path is inferred mainly from entrances, exits, or layout |
| D | Draft Misaligned | Draft geometry is visibly shifted; flag it, then repair the geometry |
| E | Task Mismatch | The feature may exist but is outside the robot navigation task |
| U | Unsure | A reliable decision is not possible yet; leave it for review |

The key distinction is: **Weak Visual requires identifiable supporting evidence in the RGB image.** If the path is inferred mainly from layout or common sense rather than visible pixels, mark Context Only. Low resolution alone is not automatically B; if you can only guess, use C.

In Evidence mode, **E is a local Task Mismatch span**: it excludes only the selected interval. Excluding the entire polyline requires the explicit **Exclude Entire Path** action in the context menu or inspector. The whole path becomes muted grey and can be restored with **Restore Entire Path**; both actions support undo/redo.

Color key: amber dashed = unreviewed; green = A Clear Visual; orange = B Weak Visual; purple = C Context Only; red = D Draft Misaligned; grey = E Task Mismatch; blue-grey = U Unsure.

For B, the inspector optionally records `visibility_issue`: `tree_canopy`, `shadow`, `low_contrast`, `low_resolution`, `narrow_structure`, `building_occlusion`, `mixed`, or `other`. Leaving it unspecified is valid. Repainting B as another class clears the field.

### Step 4: check before moving on

- [ ] Major roads, visible small paths, sidewalks, garden paths, and connectors are covered.
- [ ] Every line is the canonical centerline of a stable navigable corridor, not an arbitrary robot trajectory.
- [ ] No divided road is represented by a line on its center separator.
- [ ] No geometry extends outside the image.
- [ ] Every path span has an A/B/C/D/E/U label.
- [ ] Any D geometry that was repaired has been relabeled A/B/C/U.
- [ ] Unclear imagery has not been treated as reliable A evidence.
- [ ] An empty image is marked reviewed only after confirming it truly has no target path.

Click **Save + Next** or press `Ctrl/Cmd + Enter`. The tool writes JSON only and never changes original RGB files.
