# Remotion Studio 管线设计 v1

> 2026-10-06 · 回应「做 studio：24 史批量产脚本 → Remotion 渲染 → 行军/击败/斩杀动画可复用」
> 结论：**可以。而且项目已经建好约 70% ——缺的不是架构，是「把已有 IR 接到 Remotion 上」和「24 史→脚本的前端」。**

---

## 一、现状盘点（先看清手里有什么）

| 资产 | 位置 | 状态 |
|---|---|---|
| **二十四史全文（全译本）** | `02_数据/史料文献/二十四史全译01–24.txt` | ✅ 24 部全在（史记 2.6MB / 晋书 4.1MB / 宋史 9.8MB） |
| **IR 中间表示（JSON）** | `01_工作流/examples/*.director.json`（13 个） | ✅ schema 已定，已跑过 v1–v5 迭代 |
| **作者层格式（Markdown+YAML）** | `01_工作流/SCRIPT_FORMAT_v1.md` | ✅ `historymap-v1` 区块规范 |
| **编译器 + 校验器** | `compile_script.py`(350行) + `compile.py`(558行) | ✅ 校验时窗/槽位/source_ids/禁像素坐标 |
| **地名解析器** | `place_lookup.py` + `places_curated.json` | ✅ 地名别名 → 坐标（**这就是防幻觉的校验器**） |
| **动作库** | `ACTION_LIBRARY.md` | ⚠️ 只有 `death`/`ascend`/`depose` + 城池 4 tier |
| **历史地图数据** | 谭其骧图集18期 / CHGIS / 行政区SHP 9朝 | ✅ |
| **AE 后端** | `build.jsx` + `run.py` | ✅ 能出 .aep |
| **Remotion 管线** | `remotion-shuihong/` | ⚠️ **脚本硬编码在 `Root.tsx` 的 `SHOTS: BW[]`，没接 IR** |
| **24 史 → 脚本的抽取前端** | — | ❌ **完全空白** |

**一句话：IR 有了、编译器有了、物料有了，但 Remotion 这条腿是"裸的"（手写 TSX），而且没有从史料自动生成脚本的入口。**

---

## 二、核心架构决定

### 决定 1：只保留一个 IR —— `director.json`

**不建第三套格式。** 现有 `director.json` 已经是可用的中间表示，字段覆盖：

```
id / title / storyYear / durationSec / canvas / assets / view
regions / labels / routes / markers / camera / sources / narrationText / beats / sourceNote
```

管线变成：
```
24史TXT →[抽取]→ director.json →[校验]→ →[人审]→ →[后端渲染]→ 视频
                        （唯一IR）              ├─ AE 后端（已有，build.jsx）
                                               └─ Remotion 后端（待建）
```

**为什么重要**：IR 是唯一资产，后端可替换。将来 Remotion 换成别的引擎，脚本一行不用改。

### 决定 2：Remotion 后端要"读 IR"，不是"手写 TSX"

现在 `Root.tsx` 里 `const SHOTS: BW[] = [...]` 是**反模式**——改一集要改代码。目标：

```tsx
const episode = await loadDirector("public/scripts/bawang-301.director.json");
export const RemotionRoot = () => <EpisodeComposition episode={episode} />;
```

**改脚本 = 改 JSON，不碰代码。** 这是"批量"能成立的前提条件。

### 决定 3：复用的是"行为 + 时序曲线"，不是素材

> **这是整个设计里最容易做错的一点。**

唐代的行军和汉代的行军，**动作曲线相同、素材不同**（底图/字体/城池符号/配色）。所以 verb 组件里**绝对不能硬编码**颜色、字体、底图——全部由 `episode` 注入。否则复用就会变成"一改颜色全崩"。

---

## 三、动作复用设计（回答"行军/击败/杀死怎么复用"）

### 三层抽象

| 层 | 内容 | 谁来写 |
|---|---|---|
| **① 动作原语（verb）** | 语义：`march`/`defeat`/`kill`/`capture`… | 一次定义，全项目共用 |
| **② 参数 schema** | 每个 verb 声明必需参数（actor/target/place/时间窗） | 编译器校验 |
| **③ Remotion 实现** | 一个 verb = 一个组件；外观由 episode 注入 | `ActionLayer.tsx` |

### 原语表（建议 15 个，覆盖 24 史绝大多数事件）

| verb | 语义 | 必需参数 | 视觉实现 |
|---|---|---|---|
| `march` | 行军 A→B | actor, from, to, 时间窗 | 路线箭头推进（已有 `RouteArrow`） |
| `defeat` | 击败 | winner, loser, place | 双箭头相撞 → 败方后退碎裂 |
| `kill` | 斩杀 | killer, victim, place, stamp | 人物牌灰化 + 印章"诛/卒/赐死"（已有 `death`） |
| `capture` | 攻取城池 | place, actor, from→to | **已有 `useCapture` 四步**（进军→抵达→易主→标注） |
| `siege` | 围城 | place, actor, 时长 | 包围光晕环收拢 |
| `fall` | 陷落 | place, actor, year | 城点变暗 + 裂纹 |
| `ascend` | 即位/称帝 | actor, title, place | 金冠 + 旗帜升起（已有） |
| `depose` | 废黜 | actor, victim | 横木 + 缩至 85%（已有） |
| `usurp` | 篡位 | actor, victim | 已有（`Event.type`） |
| `raise` | 起兵 | actor, place | 已有（`Event.type`） |
| `defect` | 叛/降 | actor, from→to | 旗帜变色 |
| `flee` | 出奔 | actor, from, to | 快速箭头 + 残影 |
| `enfeoff` | 封王/册封 | grantor, grantee, land | 色块分配动画 |
| `ally` | 会盟 | parties, place | 双色连线 |
| `move_capital` | 迁都 | from, to, year | 都城标记平移 |

**粒度经验：15–25 个是甜点区。** 少于 10 个覆盖不住，多于 40 个组合爆炸（且要维护 40 个组件）。

### 现成的样板

`CaptureLayer.tsx` 已经是一个**合格的原语实现**：`useCapture(frame, startFrame, dur)` 把"攻取"拆成四步时序，`CityMarker` 的 `attacker` 参数负责易主换色。**它该被提升为通用 `ActionLayer`，而不是留在八王之乱专用文件里。**

---

## 四、五个真实约束（必须知道，否则会踩）

### ① 24 史 ≠ 24 部可视频化

志、表、书 **基本没有空间事件**。以《晋书》130 卷为例，有事件密度的是**本纪 10 卷 + 载记 30 卷**（约 31%），志 20 卷几乎无空间事件。

**所以"批量"的正确姿势是按事件密度选题，不是无脑全量跑。** 先做一个"事件密度扫描器"，把 24 史里能成片的部分筛出来。

### ② LLM 抽地名/年份/人物是最大幻觉源

文言文里"河内""颍川"既是郡名又是地名，"王浚/王濬"同音异写。**必须机器校验**：
- 地名 → 必须命中 `places_curated.json`（已有 `place_lookup.py`）
- 年份 → 必须落在史料所属朝代区间内
- 人物 → 必须在 `characters` 表里有定义

**这个校验器是你能赢过白虹说/史图记忆簿的地方——他们靠人肉，你靠机器 + 人审双保险。**

### ③ 同事件多源冲突

《旧唐书》vs《新唐书》、《宋书》vs《南史》同记一事常有出入。schema 已有 `source_ids` **强制字段**（编译不过就报错），务必保留冲突标记，不要静默取一个。

### ④ 素材必须按朝代切换

底图、字体、城池符号、配色都要分朝代。项目已有多套 basemap（wide/core/jin/jin_hist…），要建立 **`episode.styleProfile` → 素材映射表**，否则"复用"会退化成"每朝重做"。

### ⑤ 产能真相

现在一集是手写 ~200 行 TSX。要"批量"，**必须把单集从"2 天"压到"2 小时"**。压缩点不在渲染，在**脚本外置**（决定 2）和**动作复用**（第三节）。

---

## 五、落地路线（按性价比排序）

| 阶段 | 内容 | 为什么排这 |
|---|---|---|
| **P0** | Remotion 读 `director.json`，`Root.tsx` 去掉硬编码 | **半天，纯搬运，不改渲染逻辑，收益最大** |
| **P1** | 把 `CaptureLayer` 提升为通用 `ActionLayer`，补齐 `march`/`defeat`/`kill` | 1–2 天，复用能力从 5 个 verb → 15 个 |
| **P2** | 24 史 → `director.json` 抽取器（扫描→抽取→对库校验→候选脚本） | 3–5 天，这是"批量"的入口 |
| **P3** | 审核台 + 批量调度（人审卡点、任务队列、失败恢复） | 前面稳了再做 |

**P0 是必做且立刻能做的。** 做完它，"批量"才有落脚点——否则抽出来的脚本没地方喂。

---

## 六、明确不做

- ❌ 不建第三套脚本格式（用 `director.json`）
- ❌ 不在 verb 组件里硬编码颜色/字体/底图
- ❌ 不做"全量 24 史一键出片"（志表书没有空间事件，跑出来是废片）
- ❌ 不取消人审卡点（历史内容不可静默修正，源数据异常必须如实记录）
- ❌ 不在 P0 之前动渲染效果（脚本没外置，改效果是白改）

---

## 七、与已有文档的关系

| 文档 | 关系 |
|---|---|
| `SCRIPT_FORMAT_v1.md` | **作者层照用**，`historymap-v1` YAML 就是写脚本的手感 |
| `ACTION_LIBRARY.md` | **需要扩展**：从 3 个人物动作 → 15 个含战争动词的原语 |
| `STUDIO建设与制作主链大纲.md` | 宏观流程参考；本文补充的是 **Remotion 这条技术腿** |
| `GEOlayers3历史Studio实施大纲.md` | AE 路线；本文的 Remotion 后端与之并行，共用 IR |
