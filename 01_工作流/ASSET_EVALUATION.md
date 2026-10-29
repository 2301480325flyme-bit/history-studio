# 新增历史视频素材逐项适用结果

日期：2026-09-29。素材根目录：`D:\history\codex2\历史视频素材库`。这里记录的是本机制作工作流的可用性，不替代历史事实、底图版权或素材许可审查。

| 优先级 | 用户提供的方向 | 适用结果 | 证据与下一步 |
| --- | --- | --- | --- |
| 1 | 按年份切换疆域、区域填色 | **已接入并导出。** `snapshots` 每年独立选择 GeoJSON 要素，同投影生成填色/边界图层；年份文字同步切换。图层在分界处先淡出再淡入，不生成中间年份形状。 | `examples/world-jin-year-switch.director.json`、`output/world-jin-year-switch/world-jin-year-switch.aep` 与 MP4。300/400 年 `Jin` 均为 `BORDERPRECISION=1`，编译时柔化填色边缘，AE 降低边界描线不透明度。数据只适合本地参考样片。 |
| 2 | 地名定位标签、定位点 | **已接入并导出。** `placeId/placeName + year` 自动解析坐标与当年名称，`labels[].point` 产生原生 AE 点位，`start/end` 控制文字和点位的时间。 | `world-jin-year-switch` 样片示范 300 年邺城/建邺、400 年建康。`places.geojson` 未收录这两处，因此在 `places_curated.json` 登记有来源的近似点位；编译器拒绝把 300 年南京古城称为建康。 |
| 3 | 行军线、箭头、路线跟随 | **原工作流已可用。** 路线按经纬度投影，Trim Paths 生长，箭头沿采样路径移动；教程的光晕/亮芯版已接入。 | `examples/three-kingdoms-motion-upgrade.director.json` 和 `output/course-upgrade/`。当前样例路线为技术示意，不能作为史实。 |
| 4 | 镜头推进与 3D 地形 | **镜头推进可用，3D 地形未接入。** `camera` 驱动 AE 地图父级空对象的位移和缩放。现有地形保持平面配准，便于叠加历史疆域。 | 两份样片都含镜头运动。参考工程中的 Element 3D/C4D/GEOlayers 依赖及渲染许可未就绪，不用其工程直接生产。 |
| 5 | 边界描线、局部高亮 | **已接入并导出。** 年份快照有独立边界图层；上一轮 `focus` 按已配准政权蒙版使背景压暗、目标区域微亮。 | `world-jin-year-switch` 与 `course-upgrade` 样片。对于边界精度 1/2/3，快照描线强度分别为 34/56/78%。 |
| 6 | 河流、海面、云雾、雨雪 | **素材与课程可供分镜参考，未作为通用默认层。** 当前样片没有水战、天气或季节叙事，加入会遮挡地图主信息。 | 确定事件、时空和授权后，按镜头添加原生 AE 图层或有授权素材；不运行归档中的第三方插件/安装文件。 |
| 7 | AE 参考工程 | **已读项目收集报告，未复用工程/缓存瓦片。** 报告列出 Place Top/Bottom/Left/Right、Region、Locator 等合成，可借鉴点、区、标签分层方式。 | `07_AE参考工程/无标题项目/无标题项目报告.txt`。自动工作流已用原生 AE 图层实现地点与区域，避免把 Esri 瓦片和插件依赖带入导出。 |
| 8 | 两份使用手册 | **已检查内容结构。** AE 快捷键文档是简短基础命令；GEOlayers 手册以画面为主，适合人工操作查阅。 | 对脚本生成与批量渲染暂无比已实现流程更直接的规则。 |

## 世界地图资料的边界

- 上游 [README](https://github.com/aourednik/historical-basemaps) 明确把地图称作进行中的基础图，并建议使用前与其他来源比对。其 `NAME/SUBJECTO/PARTOF/BORDERPRECISION` 等属性有助于筛选和呈现可信度。
- 本地 `world_300.geojson` 的同一要素出现 `NAME=Jin`、`ABBREVN=Han`；`world_400.geojson` 的 `ABBREVN=Jin`。这类元数据不一致需要逐年核查。
- 上游 [issue #74](https://github.com/aourednik/historical-basemaps/issues/74) 截至本次核对仍为 Open，讨论 GPL-3.0 是否意图覆盖 GeoJSON 数据。样片只作为本地技术验证；公开视频、商用和再分发前须明确数据许可。
- 这套数据没有 311 年快照，300 年和 400 年的低精度面不能代替“永嘉之乱”事件年的准确疆界。镜头要讲 311 年，可先使用地点、路线和文字；精确边界需要相应年份并经审校的数据。

## 自动化输入与交付

新增输入：顶层 `snapshots[]` 的每项必须填 `year=sourceYear`、`start/end`、`territories`、`nameField`、`regions[]`。快照须从 0 秒连续覆盖片尾，不允许相互重叠。`labels[].point` 和 `labels[].start/end` 可选。

运行：

```powershell
python zcode/ae-workflow/run.py zcode/ae-workflow/examples/world-jin-year-switch.director.json --out zcode/ae-workflow/output/world-jin-year-switch
```

输出有分层 PNG、`source-manifest.json`、`run.jsx`、`ae-job.json`、可编辑 AEP、MP4、渲染日志和媒体元数据。本机最终样片为 16 秒、1920×1080、30 fps、H.264/AAC。长 AVI 在内存紧张时会自动分段编码。
