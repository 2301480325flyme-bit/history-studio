# handoff.md · HistoryMap Studio 交接文档

> 最后更新：2026-10-06
> 交接人：WorkBuddy（Codex）
> 文档要求：**每条命令都实测可跑**。如果你发现某条跑不通，说明环境变了，请更新本文档。

---

## 0. 一句话定位

> **半自动历史地图纪录片生产系统 v0.1**
>
> 机器负责**检索、整理、定位、生成镜头骨架**；
> 人负责**史实判断、叙事取舍、旁白表达**。

**不是**"自动历史视频生成器"。这个区别是本项目能长期做下去的前提。

---

## 1. 五分钟快速上手

```bash
# 环境
PY=C:/Users/23014/.workbuddy/binaries/python/versions/3.13.12/python.exe
NODE=C:/Users/23014/.workbuddy/binaries/node/versions/22.22.2-3/node.exe
cd "D:/history/codx_3 history studio/01_工作流"

# ① 从语料抽事件候选
cd maindata
$PY extract_events.py extract 晋书 --juan 帝纪第四 --out cand.json

# ② 自动成分镜骨架
$PY auto_episode.py cand.json --anchor-only --episodes 3 --shots-per-episode 6 \
    --out-dir "../remotion-shuihong/public/scripts" --prefix bw

# ③ 注册 + 渲染（不碰任何 TS 代码）
cd ../remotion-shuihong
#    在 public/scripts/manifest.json 追加一条 {id, episodeId, title}
$NODE node_modules/@remotion/cli/remotion-cli.js render <合成id> out/成片.mp4
```

---

## 2. 完整生产线（★ 是人工环节，不可删）

```
原始史料
  ↓  build_corpus.py               清洗 → corpus/*.jsonl（26 部 / 29.9 万段）
  ↓  extract_events.py             事件抽取 → 带 sourceId / 纪年 / 实体
  ↓  （主表链接）                    placeId ↔ 坐标
  ↓  auto_episode.py               分镜骨架：focus / basemap / action / year
  ↓                                ★ narrationHint（原文+出处+纪年）
★ 人工 / AI 编辑阶段 ← 选事件、合并、删掉跑偏的、写旁白、定镜头重点
  ↓  manifest.json                 注册（改数据，不改代码）
  ↓  remotion render               成片
```

**★ 这一步不能删。** 实测证据：自动抽取的 26 条有地点候选里大多数是李特/张昌流民起义，
而八王主线事件（伦篡位、冏起兵、颙表冏…）**全部漏掉**。
自动化能把 89 条排好序铺在地图上，但**选哪 6 条是叙事判断**。

---

## 3. 目录地图

| 路径 | 内容 |
|---|---|
| `01_工作流/maindata/` | **主表与全部 Python 工具**（15 个脚本） |
| `01_工作流/maindata/places.json` | 正式地名表（13 条，**可考证**） |
| `01_工作流/maindata/places_approximate.json` | ⚠️ 近似地名层（28 条，**全部 approximate**） |
| `01_工作流/maindata/persons.json` | 正式人物表（8 人 = 八王） |
| `01_工作流/maindata/persons_approximate.json` | ⚠️ 近似人物层（21 条，**全部 unverified**） |
| `01_工作流/corpus/` | 26 部史书的清洗结果（`.jsonl` + `.txt`） |
| `01_工作流/remotion-shuihong/src/` | 渲染端（19 个 TS/TSX） |
| `01_工作流/remotion-shuihong/public/scripts/` | 脚本 JSON + `manifest.json` |
| `01_工作流/remotion-shuihong/public/basemap_*.png` | 三层底图 |
| `02_数据/史料文献/word版/` | ★ **主源**：23 部文言原文 `.doc` |
| `02_数据/史料文献/二十四史全译*.txt` | 旧源（白话译文，有损坏，**尽量别用**） |
| `06_报告/` | 候选事件 JSON、报告 |

---

## 4. 铁律（违反即错）

### 4.1 数据可信度
1. **坐标宁可缺，不可编。** 没有出处就标 `approximate` 或 `unregistered`，不许填"大概是"。
2. **`approximate` / `unverified` 不得升级为 `confirmed`**，除非补上 `coordinateEvidence`。
3. **不得静默修正源数据异常。** 发现矛盾要登记（如 `PERSON_CORRECTIONS` / `coordinateEvidence`），
   并保留原文依据。
4. **行政层级必须看 `TYPE_CH` 字段**，不许把「图层里的面」当「州界」。

### 4.2 自动化边界
5. **自动化到「骨架」为止，不自动化「表达」。** 旁白/台词留空，由撰写者读史料后落笔。
6. **不编造历史内容。** 模板/脚本生成的旁白一律留空 + 给 `narrationHint`。

### 4.3 工程
7. **改脚本 = 改 JSON，不改 TS。** 新增一集只需在 `manifest.json` 追加一条。
8. **必须单独跑 `tsc`。** Remotion 的 `render` 不会因类型错误失败，会静默带过。
9. **主表会被重建覆盖。** 手工追加的条目活不过一次 `build_maindata.py` —— 所以近似层单独放文件。

---

## 5. ⚠️ 已知陷阱（都是踩过的）

| 陷阱 | 现象 | 正确做法 |
|---|---|---|
| **CRLF 被 `clean()` 转成 `\r`** | 任何 CRLF 换行的 TXT 解析失败，整篇变成一个巨型「行」 | TXT 分支必须用 `re.split(r"[\r\n]+")` |
| **`build_maindata.py` 覆盖手工追加** | 手工加进 `places.json` 的条目下次重建即消失 | 近似层放独立文件（已这么做） |
| **`view_bounds` 层级混淆** | 把 45 条**郡**级 polygon 报成「州级」 | 用 `probe_chgis.py` 看 `TYPE_CH` |
| **Remotion `still` 不报类型错误** | 类型错了也照样渲染成功 | 单独跑 `tsc --noEmit` |
| **符号被 `project()` 算出画面外** | 地点明明有坐标却不显示 | 焦点在底图范围外时改用更宽的层级（`pickBasemap`） |
| **`.doc` 是 OLE 二进制** | `python-docx` 不支持 | `olefile` 读 `WordDocument` 流 → **UTF-16LE** 解码 |
| **段落分隔符** | 硬换行的 TXT 无法按段落切 | 去掉硬换行后按句读切（word 版是单 `\r`） |
| **中文没有词边界** | 「敢距**王命**」里的「王」被当封号 | 两阶段：先建封号白名单，再只在白名单后抽名 |
| **《晋书》几乎不用全名** | 搜「司马颙」0 次、搜「河间王」89 次 | **别名表以封号为主**，全名几乎无用 |

---

## 6. 脚本清单（全部实测可跑）

| 脚本 | 用途 |
|---|---|
| `build_corpus.py` | `.doc` / `.txt` → `corpus/*.jsonl`（25 部需按 4 种结构自适应） |
| `build_maindata.py` | 汇总主表；含 `PERSON_CORRECTIONS`（史实订正） |
| `resolve_dynasty.py` | 坐标统一 + 剥离为 `*.byid.json`；传导人物订正 |
| `extract_events.py` | 事件抽取（`scan`/`entities`/`extract`），带 `sourceId` + 年号换算 |
| `auto_episode.py` | 候选事件 → 可渲染 episode（`--anchor-only` / `--prefer-anchor`） |
| `compile_story.py` | 叙事模板 → episode（模板驱动路径） |
| `maindata.py` | 查询 + 校验：`check` / `assets` / `place X 301` / `person X` / `era X` |
| `find_places.py` | 从语料发现主表缺失的高频地名 |
| `find_persons.py` | 两阶段人物识别（封号白名单 → 抽名） |
| `add_region_places.py` | 生成州级地名**近似层**（现代同名城市坐标，明确标 approximate） |
| `add_persons_approximate.py` | 生成人物**近似层**（词频候选，全 unverified） |
| `extend_ranges.py` | 从语料实测地名年代范围并扩写 `names` |
| `probe_chgis.py` | CHGIS 字段诊断（**层级判定必须用它**） |
| `check_pdf.py` | 判断 PDF 有无文字层（决定能否直接抽文本） |
| `pdf_lookup.py` | 影印 PDF 按页导出图片，供人工核对 |

---

## 7. 渲染端组件

| 文件 | 职责 |
|---|---|
| `geo.ts` | **投影与底图层级的唯一真相源**：`VIEW` / `VIEW_BOUNDS` / `pickBasemap` / `BASEMAP_FILE` |
| `DirectorComposition.tsx` | 读 `scripts/<id>.json`，用 `Sequence` 串联全部镜头 |
| `DirectorShot.tsx` | 通用镜头组件（数据驱动，非硬编码） |
| `Symbols.tsx` | 18 个地点符号 + 10 个状态 + 图例 |
| `ActionLayer.tsx` | **15 个事件动词**（march/defeat/kill/siege/fall/capture/ascend/depose/usurp/raise/defect/flee/enfeoff/ally/move_capital） |
| `Camera.tsx` | 墨迹转场 `ink_bleed` / 卷轴 / `hold` / `shake` |
| `Layers.tsx` | 疆域生长 / 边界流动 / 地名浮现 / 年份跳变 |
| `MainData.ts` | 主表加载（**含近似层叠加 + `personsVerified` 白名单**） |

### 三层底图
| 层级 | 覆盖 | scale | 说明 |
|---|---|---|---|
| `national` | 69.06–139.07°E / 16.64–48.92°N | 1571.5 | **只负责覆盖**，不追求城市特写（z6 瓦片） |
| `wide` | 104.3–122.7°E / 30.9–39.3°N | 6000 | 原有，未改动 |
| `core` | 109.4–117.6°E / 33.3–37.1°N | 13500 | 原有，中原核心 |

> ⚠️ **`national` 的 center/scale 是从瓦片范围反算的**（经度算得 1571.4、纬度 1571.5，偏差 0.01%）。
> **改参数必须重新反算，不能手调** —— 手调会让经纬度与像素脱钩。

---

## 8. 语料现状

- **26 部 / 29.98 万段 / 3,256 万字 / 损坏率 0.535%**
- 25 部来自 `word版/*.doc`（文言原文），1 部（旧五代史）来自全译本 TXT
- 覆盖八王之乱的 CHGIS 数据：**49 条，全是郡级，州级 0 条** → 疆域层暂不可用

---

## 9. 未完成 / 下一步建议

### 已知问题（不阻塞）
1. 同位置动作标签重叠（第 5 镜「执乂」被涟漪盖住）
2. 三层底图风格不统一（`national` 无水系，`wide`/`core` 有）
3. 字幕两行时第二行居中，排版略怪
4. 「冏」字形渲染可疑

### 建议的下一步（按优先级）
1. **先把八王之乱这 6 镜的旁白逐句对一遍原文** —— 验收报告里已标了哪句是原文、哪句是撰写者的概括。
   确认无误后生产线即可定为"可用"。
2. **然后再做永嘉之乱** —— 它会真正压测全国底图、地点消歧、事件筛选
   （涉及洛阳、并州、平阳、河东、长安）。
3. 人物识别暂停（投入大、短期收益低）。需要旗标/阵营时再扩 `persons_verified`。
4. 疆域层推后，等有西晋**北方**州级数据再说。

---

## 10. 关键设计决策（改动前请理解）

1. **只有一个 IR**：`director.json` / episode JSON。Remotion 与 AE 共用。
2. **复用的是「行为 + 时序曲线」，不是素材。** 组件禁止硬编码颜色/字体/底图。
3. **数据分层**：全局主表（一次性）→ 每集脚本（只引 id）。
4. **`narrationHint` 是证据包，不是台词。** 原文保留供回溯，台词由人写。
5. **近似层与正式层物理隔离。** 前者 `approximate`/`unverified`，运行时叠加，随时可弃。
   目的：防止"抽出来了所以画上去了"。

---

## 11. 相关文档

| 文档 | 内容 |
|---|---|
| `01_工作流/maindata/README.md` | 主表使用说明（**先看这个**） |
| `01_工作流/maindata/生产线验收报告.md` | 全流程验收结果 + 发现的问题 |
| `01_工作流/maindata/长任务实施报告.md` | 20 项待办的实施记录 |
| `01_工作流/corpus/构建报告.md` | 语料构建统计与损坏模式 |
| `01_工作流/视觉符号与动画库-v1.md` | 符号/动画的完整设计 |
| `01_工作流/Remotion-Studio-管线设计-v1.md` | 管线架构与约束 |
| `06_报告/八王之乱-事件候选.json` | 89 条候选事件 |

---

## 12. 一句话给下一个人

> **别再往"更全自动"的方向使劲了。**
> 现在缺的不是自动化，是**有人真的拿一集去做，把旁白写对**。
> 管道已经通了，剩下的是内容判断 —— 那才是这个项目真正的价值所在。
