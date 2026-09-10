# Annotation Schema V2

V2 的标注单位是 image/canvas native pixel 坐标中的 Complete Path Polyline。Path Type 描述“这是什么路”，Evidence 描述“这一小段在 RGB 中有什么依据”，二者不能混成一个标签。

## 1. 最小结构

```json
{
  "schema_version": 2,
  "image_id": "tongli/r001_c004_z19",
  "image": {
    "source_path": "rgb/tongli/r001_c004_z19.png",
    "width": 1024,
    "height": 1024,
    "region": "tongli"
  },
  "annotation_status": "unreviewed",
  "review_scope": "partial",
  "segments": [
    {
      "edge_id": "e000012",
      "path_type": "pedestrian_path",
      "points": [[110.0, 240.0], [340.0, 260.0], [610.0, 410.0]],
      "source": "manual",
      "evidence_spans": [
        {
          "start_s": 0.0,
          "end_s": 126.4,
          "evidence": "clear_visual",
          "review_confidence": "medium",
          "note": ""
        }
      ],
      "excluded_from_task": false,
      "whole_path_exclusion_confirmed": false,
      "geometry_review_required": false,
      "geometry_fixed": false,
      "review_status": "unreviewed"
    }
  ],
  "ignore_regions": []
}
```

`source_path` 应为 dataset 内相对路径。原始 RGB 不嵌入 JSON，也不由标注器改写。

## 2. Evidence arc-length 坐标

`start_s` / `end_s` 是从 polyline 第一个点起，沿折线累计的 native-pixel 弧长。它允许 span 边界位于任意线段内部，不依赖控制点 index。

插入或移动控制点时，V2 按旧总长与新总长的比例重映射 span，使原来位于路线 20%–60% 的审核区间仍保持在大约 20%–60%。Evidence 边界不会迫使可见 geometry 增加控制点，因此撤销简单，也不会产生大量碎 path。

同一 edge 的 span 按 `start_s` 排序，不应重叠。对已有区间重新赋值时，只切分 evidence interval，`points` 不变。相邻且 evidence/confidence/note/visibility_issue 相同的区间会合并。

## 3. Evidence 值

| 值 | UI 键 | 默认训练处理 |
|---|---|---|
| `clear_visual` | A | positive valid |
| `weak_visual` | B | positive valid |
| `context_only` | C | ignore |
| `draft_misalignment` | D | ignore，并设 `geometry_review_required=true` |
| `task_mismatch` | E | excluded local span，保留 source geometry |
| `uncertain` | U | ignore |

D 的 geometry 由人工修正并标 `geometry_fixed=true` 后，仍需把对应 span 重新赋为 A/B/C/U；D 本身不会进入 positive。未审核长度同样导出为 ignore，未标区域不能自动视为 background。

### Local E 与整路排除

`task_mismatch` 是局部 Evidence span 属性。局部 E 只排除选中的弧长区间；它不会设置 `excluded_from_task`，也不会排除同一条路线上的 A/B 区间。只有用户明确执行“排除整条路径”时，才设置 `excluded_from_task=true` 与 `whole_path_exclusion_confirmed=true`。

整路排除仍保留原始 polyline，导出到 `excluded_edges`；恢复整条路径只会清除整路标志，不会删除局部 E。旧版同时存在局部 E 和 `excluded_from_task=true` 的文件会被标记 `legacy_exclusion_ambiguous=true`，导出进入 `ambiguous_exclusions`，必须人工确认，程序不会猜测用户意图。

### Weak Visual 辅助原因

`weak_visual` 可以有可选的 `visibility_issue`，枚举为：`tree_canopy`、`shadow`、`low_contrast`、`low_resolution`、`narrow_structure`、`building_occlusion`、`mixed`、`other`。`none` 表示未指定，未指定时字段可以省略。该字段只在 B/Weak Visual 上有效；把 B 改成其他 Evidence 时自动清除。低分辨率不自动等于 B：仍必须能指出 RGB 中的具体视觉证据，否则应标 C/Context Only。

## 4. Review 状态

每条 path 的 Evidence coverage 按弧长计算。全部 path 长度都有 Evidence 后，该 image 可以成为 `reviewed`，但 `review_scope` 仍保持 `partial`。没有 path 的 image 必须由人工点击 Mark image reviewed，不能因为空数组自动通过。只有人工点击 **Mark Full Image Reviewed** 才能设置 `review_scope=full_image`；100% Evidence 不会自动触发它。

`full_image` 只表示人工系统扫描过整张 RGB，确认目标路线没有明显漏标；它不表示所有未标像素都是可靠 background。导出继续保留警告：`Unlabelled image area is not automatically reliable background.`

`U` 是合法状态，但默认 `training_valid=false`、`evaluation_valid=false` 的语义由派生导出规则表达，不需要删除或伪装成人工确定值。

## 5. 旧数据兼容

schema 1.x 的 `edges[].polyline` 会在内存中转换为 `segments[].points`：

- `path_type`、source node id、visibility、confidence 等已知字段保留；
- 如果 Region 带 OSM/draft 来源，segment 的 `source` 为 `draft`；
- `evidence_spans=[]`、`review_status=unreviewed`，绝不自动设为 Clear；
- `nodes` 作为 `legacy_nodes` 保留，便于追溯端点来源；
- 保存写入 `annotations_v2/`，不覆盖 v1。

项目中较早的逐图导出 JSON 如果已经使用 `segments[].points` 但 schema 仍为 1.x，也能安全读入。重复 edge id 会附加 segment suffix，避免编辑时冲突。

手工批量迁移（只输出新文件）：

```bash
python scripts/migrate_annotations_v2.py path/to/legacy_annotations \
  --out-dir path/to/annotations_v2
```

已存在的目标文件默认跳过。工具不会批量覆盖源 JSON。

## 6. 派生导出

Training 与 Trusted Evaluation 导出都从 v2 生成新 JSON：

```json
{
  "valid_positive_polyline": [],
  "ignore_spans": [],
  "excluded_spans": [],
  "excluded_edges": [],
  "ambiguous_exclusions": [],
  "warning": "Unlabelled image area is not automatically reliable background."
}
```

Training：A/B → `valid_positive_polyline`，C/D/U/unreviewed → `ignore_spans`，局部 E → `excluded_spans`，明确整路排除 → `excluded_edges`。Trusted Evaluation 只含 A/B；B 保留 `visibility_issue` 用于后续按困难原因分组。它不输出 E 作为可信正例。

只读审计可运行：

```bash
python scripts/audit_v2_exclusions.py path/to/annotations_v2
```

该命令只报告整路排除、局部 E 和歧义数量，不修改任何源 JSON。
