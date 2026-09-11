# Annotation Tool V2 使用说明

这份说明给实际采图、标注和复核的同事使用。V2 的目标是把日常流程缩短为：

```text
启动程序 → 打开文件夹 → 画 / 修路线 → 审核 Evidence → 保存并下一张
```

不需要先做 manifest，不需要改 config，也不需要提前生成空 JSON。程序不会修改原始 RGB。

## 1. 启动

### 推荐：双击启动

不需要先激活虚拟环境：

- macOS：双击项目根目录的 `AMap Path Annotator.app`；
- Windows：双击 `scripts\run_annotator_easy.vbs`。

第一次启动会自动创建 `.venv` 并安装 `requirements.txt`，之后直接双击即可。电脑需要安装 Python 3.12。macOS 若第一次提示无法验证开发者，请右键应用并选择“打开”确认一次。

启动后点击 **Open Folder**，选择普通图片文件夹；重新整理的 4 人数据分别位于 `A/rgb`、`B/rgb`、`C/rgb`、`D/rgb`。

### 备用：命令行启动

在项目目录激活虚拟环境后运行：

```bash
python scripts/launch_annotator.py
```

启动页只有 **Open Folder** 和最近打开的文件夹。也可以直接运行：

```bash
python scripts/launch_annotator.py --folder /path/to/dataset
```

界面默认中文，可在顶部 **语言** 菜单中即时切换中文 / English，选择会自动记住。也可以用 `--language zh` 或 `--language en` 指定本次语言。

macOS 的 Qt Cocoa 平台插件会在程序导入 UI 前自动检查并清除异常的 hidden 标记。程序不修改系统 Qt，只处理本项目 `.venv` 里的插件。

## 2. Open Folder 能识别什么

支持 `.png`、`.jpg`、`.jpeg`、`.tif`、`.tiff` 和 `.webp`。扫描默认递归开启。

- 只有图片：立即开始标，第一次保存时创建 `annotations_v2/`。
- 图片旁有同名 JSON：自动配对。
- `rgb/` 与 `annotations/` 分开：按相对路径和同名 stem 配对。
- 多个区域子目录：相对路径参与 image identity，所以不同目录中的同名图片不会冲突。

匹配顺序严格是同目录同 stem、annotation 目录中同相对路径同 stem、JSON 内唯一的 image_id / filename。不会用模糊字符串猜测。损坏图片、损坏 JSON、孤立 JSON 或尺寸不符会进入 `files need attention`，不会挡住其他正常图片。

## 3. 界面

- 顶部：打开文件夹、选择、画路线、编辑、Evidence、撤销/重做、纯净 RGB、对照审核、缩放、保存、上一张/下一张。
- 左侧 Dataset：缩略图、image_id、审核状态、path 数和 Evidence 完成率；可搜索和筛选。
- 中央 Canvas：始终占主要空间。
- 右侧属性 / 审核 / 逐图指导 / 图层 / 检查：显示当前 path/span、Evidence 进度、每张图下一步和图层开关。
- 底部状态栏：原图尺寸、显示缩放、native 像素光标坐标和保存状态。

左右面板用 `Tab` 和 `Shift+Tab` 隐藏或恢复。

把鼠标停在主要按钮上满 3 秒，会出现“这个按钮做什么”的详细说明；鼠标移开或点击后立即消失，不会挡住连续标注。

每张图的完整中文 / English 标注清单见 [每张图片的标注指导](ANNOTATION_GUIDE_BILINGUAL.md)。

## 4. 画和改 Complete Polyline

按 `P` 进入 Draw：单击加点，双击或 `Enter` 完成；`Backspace` 撤回本次最后一点，`Esc` 取消未完成路线。程序不会自动拉直、补路或改变 geometry。

按 `V` 选择路线或控制点。拖控制点修改；双击路线 segment 插点；方向键移动选中点 1 个 native pixel，`Shift+方向键` 移动 5 px。右键可 Insert、Split、Merge、改 Path Type、**排除整条路径 / Exclude Entire Path** 或删除。整路排除会把整条线显示为灰色，并可用 Restore Entire Path 恢复；局部 E 不会触发整路排除。

Path Type 与 Evidence 是两回事。`pedestrian_path`、`vehicle_road`、`narrow_path`、`service_path` 中任何一种都可能是 Clear、Weak 或 Context。

## 5. Evidence Span

1. 按 `X` 进入 Evidence。
2. 选择区间有两种方式：按住鼠标沿同一路线拖动；或先点起点、再点同一路线上的终点（更适合触控板）。
3. 被选区间会加粗；直接按 `A/B/C/D/E/U`，不弹对话框。单击只会设置起点，不会偷偷生成一小段。
4. `N` 跳到下一个未审核区间，`Shift+N` 返回；Auto-advance 默认开启。
5. Evidence 用沿 polyline 的弧长 `start_s/end_s` 保存，不要求人工把整条线反复 Split。

类别定义：

| 键 | 名称 | 怎么判断 |
|---|---|---|
| A | Clear | RGB 里直接、清楚地看到路径 |
| B | Weak Visual | 树荫、阴影、低对比等影响明显，但仍能指出支持路径的具体像素 |
| C | Context Only | RGB 本身很难确认，主要靠入口出口、建筑布局或常识推断 |
| D | Draft Misaligned | draft / OSM 的 geometry 明显偏离可见路径；只标记问题，不自动修 |
| E | Task Mismatch | 选中的局部区间不属于机器人目标导航网络；保留 source geometry，不删除整条路线 |
| U | Unsure | 人工无法可靠决定，留给后续 review |

判断 B/C 时只问两句：B 是“我还能指出图里的具体 RGB 证据”；C 是“我主要相信这里按布局或常识应该有路”。B 可在属性面板补充 `visibility_issue`，但不要求每次都填写。

### Canonical centerline

路线不是某一次机器人实际轨迹，也不是 OSM 几何或道路边界。标注的是稳定可导航通道的标准中心线：单一 corridor 沿视觉中心；无实体分隔的窄道路只画一条；有实体中央隔离时两侧各画一条。宽广开放区域没有固定主轴时不凭感觉画线。

## 6. Clean RGB 与 Review View

按反引号 `` ` `` 进入 Clean RGB：draft、manual path、Evidence、控制点和选择框全部隐藏，只看原始 RGB。再次按键恢复。进入 Evidence mode 时会自动退出 Clean RGB，防止在看不见路线时误操作。

按 `R` 打开 Review View：左侧 Clean RGB、右侧 RGB + Annotation，zoom 和 pan 同步。这个模式用于 B/C/D 复核，不默认常开。

图层页可以分别隐藏 Draft、Manual Polyline、Evidence 和 Control Points，并调整 Draft/Evidence 透明度。Smooth / Pixel 只改变显示插值，不做 AI 放大，也不改变原图。

## 7. 保存、恢复和只读保护

- 每次编辑后 0.9 秒 debounce autosave。
- JSON 使用同目录临时文件、校验后 atomic replace；已有 v2 文件保存前留一个 `.bak`。
- 旧 schema 1.x 只读取，保存到 `annotations_v2/`，源文件不覆盖。
- 崩溃前的未保存 document 放在应用状态目录；下次打开同一图片会询问是否恢复。
- 最近 10 个文件夹、上一张图片、zoom、pan、mode、sidebar scroll 和图层显示会恢复，但不会覆盖 annotation。
- Dataset Settings 可设 **Read Only / Sealed**。只读时 Draw、Edit、Evidence、Save 和批量导出写入全部禁用。

## 8. Review 与导出

每张图按 polyline length 计算 Evidence 完成率，而不是按 edge 数。Review 页显示未审核、Weak 和 Context 长度。没有 path 的图片也可人工 Mark image reviewed。`review_scope` 独立记录 `partial` 或 `full_image`；Evidence 100% 不会自动变成 `full_image`，必须人工点 **Mark Full Image Reviewed**。`full_image` 也不表示未标像素自动是可靠 background。

Dataset 菜单提供两个派生导出，不改源 annotation：

- Export for Training：A/B 为 valid positive；C/D/U 和未审核 span 为 ignore；局部 E 为 `excluded_spans`；明确整路排除才是 `excluded_edges`。
- Export Trusted Evaluation：只导出 A/B，并保留 B 的 `visibility_issue`，便于未来按困难原因分组。

未标图像区域不会自动变成可靠 background GT。

## 9. 快捷键

| 快捷键 | 操作 |
|---|---|
| `Space + drag` / 中键拖动 | Pan |
| 滚轮 / 触控板捏合 | Zoom |
| `F` | Fit image |
| `1/2/4/8` | 100% / 200% / 400% / 800% |
| `` ` `` | Clean RGB |
| `R` | Review View |
| `V` / `P` / `X` | Select/Edit / Draw / Evidence |
| `A/B/C/D/E/U` | 给选中 Evidence span 分类 |
| `N` / `Shift+N` | 下一个 / 上一个未审核 span；非 Review 时切下一张 / 上一张 |
| `←/→` | 上一张 / 下一张；选中控制点时改为 1 px nudge |
| `Cmd/Ctrl+Z` | Undo |
| `Cmd/Ctrl+Shift+Z` | Redo |
| `Delete` | 删除选择 |
| `Cmd/Ctrl+S` | Save |
| `Cmd/Ctrl+Enter` | Save & Next |
| `Cmd/Ctrl+F` | 搜索 image_id |
| `?` | 快捷键表 |

## 10. UI 验收截图

- [默认标注界面](ui_v2/01_default.png)
- [Clean RGB](ui_v2/02_clean_rgb.png)
- [Evidence mode](ui_v2/03_evidence_mode.png)
- [Review View](ui_v2/04_review_view.png)
- [400% 精细编辑与折叠面板](ui_v2/05_zoom_edit.png)
- [中文逐图指导](ui_v2/06_image_guide_zh.png)
- [English interface](ui_v2/07_english.png)

这些截图由真实的 1024×1024 苏州卫星 RGB 与已有 draft geometry 离屏渲染生成；未对 RGB 做任何生成式处理。
