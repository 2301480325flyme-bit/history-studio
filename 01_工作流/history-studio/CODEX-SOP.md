# Codex 出片 SOP（History Studio · Remotion 路线）

给 Codex 用的单集制作流程。用户只给一句话（例如"做第 3 集群雄混战"），由你走完整条流水线，最后交付成片。
**这条路线不走 AE，也不走 `00_管理/协作` 的三角色 runner**：一个代理就能完成，自检代替独立审查。只有用户明确要求三角色制作时，才按根目录 AGENTS.md 的流程来。

**总原则：以声音为主线。** 先把故事讲好，时间轴由配音决定，画面跟着讲述走；不为凑时长或配合动画去提速、压缩停顿。

> **2026-10-24 起的默认分工是 Claude 主控、Codex 辅助**，见 `协作-Codex.md`。本 SOP 仍然是整条流水线的标准；只有用户明确让 Codex 单独做一整集时，Codex 才从头到尾照它执行。被 Claude 派活时，只做任务单里那一段。

## 0. 开工前必读（按顺序）

1. `01_工作流/history-studio/HANDOFF.md`：用户已定的决定（不要再问）、当前进度、下一集是哪集。
2. `01_工作流/history-studio/SCRIPT.md`：episode.yaml 的全部写法，包括组件、复合动作和镜头。
3. 四个规范，必须逐条执行（文件在仓库里，直接读路径）：
   - `.claude/skills/history-video/SKILL.md`：总流程、研究、地点、自检、交付；
   - `.claude/skills/history-narration/SKILL.md`：旁白、主问题、钩子、情绪节拍（最重要）；
   - `.claude/skills/history-storyboard/SKILL.md`：两秒规则、cue 对时、动词到画面的配方、镜头；
   - `.claude/skills/history-voice/SKILL.md`：配音参数和读音高风险字。
4. 样例脚本（照着写）：
   - `01_工作流/projects/sanguo-02/episode.yaml`：第 2 集，新叙事方法，复合动作用得最全；
   - `01_工作流/projects/sanguo-10min/episode.yaml`：189–280 全景版，势力配色和州郡归属可以直接复用。

## 1. 环境

- 所有命令在 `01_工作流/history-studio` 下用 PowerShell 运行，先设置 `$env:PYTHONIOENCODING='utf-8'`。
- **需要联网**：MiMo 配音和 ASR、Wikidata 地名查询都要访问网络。沙箱要允许网络访问；没有网络就停在无声排版那一步，告诉用户。
- MiMo 密钥在 Windows 用户环境变量 `MIMO_API_KEY` 里，代码会自动读取。**不要打印、写入或回显密钥。**
- 同一时间只跑一个渲染。开工前看一下 `05_项目/Remotion/studio/*/progress.json`：如果有 `"status": "running"` 且 `updated` 在 3 分钟以内，说明别的代理正在渲染，要等它完成。

## 2. 流水线

| 步 | 做什么 | 命令 / 产物 | 通过标准 |
|---|---|---|---|
| 1 研究 | 本地正史检索，整理事件表 | `python studio.py sources 关键词… --books 三国志 后汉书 --limit 15` | 每个事件至少两处出处 |
| 2 编剧 | 定主问题，写三个钩子候选并打分，按"钩/压/放/转/收"写旁白 | 写进 `projects/<id>/episode.yaml` | 符合 narration skill 的检查清单 |
| 3 地点 | 批量查询；库里没有的先查本地谭图 `02_数据/历史地图集`，再用 Wikidata，然后入库 | `python studio.py places 地名… --year 195 --web`；`place-add …` | 精度写清楚 |
| 4 落子 | 写 beats、owners、复合动作、镜头；动作优先用手绘动作库（storyboard skill 第八节），音效按第九节可选 | episode.yaml | — |
| 5 校验 | | `python studio.py check ..\projects\<id>\episode.yaml --json` | 没有 error |
| 5.5 地图一致性 | 疆域只写 `map: 年-月`（来自 `series/三国到隋/疆域.yaml`），旗牌落在他人地盘要写 `guest: true` | `python consistency.py --series s01e` | 合计 0 处 |
| 6 无声排版 | | `python studio.py build ..\projects\<id>\episode.yaml --voice placeholder --build P1`，然后 `python studio.py still ..\projects\<id>\episode.yaml -t <每拍中点…>` | **逐张打开抽帧图看**：没有遮挡，焦点在画内，箭头方向正确 |
| 7 配音构建 | | `python studio.py build ..\projects\<id>\episode.yaml --build M1` | `voice/asr-report.md` 每句一致度不低于 0.92；低于的改写台词 |
| 7.2 审片单 | 每拍一张缩略图 + 自动标记要听的拍（读音存疑、台词被大幅提速、旁白过慢/过长） | `python review.py ..\projects\<id>\episode.yaml` → `<构建>/审片单/` | 自己先看一遍，修掉明显问题再给用户 |
| 7.5 预览 | 不渲染，先在 Remotion 实时预览里给用户看；同时给用户审片单 | `.claude/launch.json` 里的 remotion-preview 配置指向本次构建的 `public` 目录 | **用户确认后才渲染** |
| 8 渲染 | 用户确认后，**后台运行**，见第 3 节 | `python studio.py render ..\projects\<id>\episode.yaml` | `media-check.json` 里 `full_decode_ok: true` |
| 9 成片自检 | 看 `contact-sheet.jpg`；每隔 2 秒抽帧，确认画面在动 | 见第 4 节 | 见第 4 节 |
| 9.5 发布包 | 三种比例封面 + B 站/抖音标题简介话题 + 章节时间 + 字幕 srt | 在 episode.yaml 写 `publish:`（hook / big / hero / at / summary / tags / next），然后 `python publish.py ..\projects\<id>\episode.yaml --build <已渲染的构建>` → `<构建>/发布/` | 章节时间对应**实际渲染的那一版**；声明里有 AI 生成。**写稿时就把 publish 写全**（缺 hook/summary/tags/next 校验会警告）；用户在网页工作台每集的「发布」页直接复制，发布时不再问人（2026-10-13） |
| 10 交付 | 更新 HANDOFF.md 进度，刷新文件清单，向用户汇报 | 见第 5 节 | — |

背景音乐：`episode.yaml` 顶层写 `music: {default: 权谋}`（可加 `db`、`duck_db`、`fade`），某拍写 `music: 战争` 或 `music: none` 切换，交叉淡入淡出、人说话时自动压低。情绪→文件在 `03_素材/音乐/library.json`，只收可商用音乐并写 `credit`（自动进发布简介）。

构建编号不要覆盖：无声排版用 P1、P2…，配音版用 M1、M2…。改了旁白再构建时，只有改过的句子会重新合成。

## 3. 长任务（渲染）

8 分钟成片约 15000 帧，在这台电脑上要渲染约 1 小时；2 分钟一集约 15 分钟。命令可能超出你的单次执行时限，所以要后台运行：

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUNBUFFERED='1'
Start-Process -WindowStyle Hidden powershell -ArgumentList '-NoProfile','-Command',"cd '$PWD'; python studio.py render ..\projects\<id>\episode.yaml *> '..\..\05_项目\Remotion\studio\<id>\渲染进度.log'"
```

然后轮询 `05_项目/Remotion/studio/<id>/progress.json`：
- `stage` 依次是 配音 → 渲染 → 编码 → 检查 → 完成；`status: done` 表示结束；`stage: 失败` 时看日志。
- 网页 Studio 的「构建与渲染」页也会显示这个进度。
- MiMo 返回 429 限流时，程序会自动退避重试，不用管。
- 不要并发跑两个 build 或 render。

## 4. 成片自检（不能只看代码测试）

1. 打开 `contact-sheet.jpg`，逐格检查：地图有没有空洞，标签有没有遮挡，字幕有没有压住其他元素，势力颜色对不对。
2. 每 2 秒用 ffmpeg 抽一帧，与上一帧做差，找出连续 4 秒以上几乎不动的段落。这类段落要补动画或 camera。
3. 抽几帧放大看关键动作：行军、交战、易手、归附是不是真的画出来了。
4. 发现问题就改 YAML，做新的构建，不要覆盖旧的。最多返修三轮，还解决不了就如实报告。

5. **逐拍自查（2026-10-23 起必做）**：按 history-storyboard skill 第十六节，逐拍检查旁白主语、箭头含义、地盘变色时机、因果交代、人马连续、读音、长时间静止、史料对应；`check` 里所有「行军：」警告必须处理或说明理由。交付时在回复里列出查过的项目和改动。
6. **新立绘**：按 history-portrait 第二节之二先写相貌档案，生图后跑 `tools/portrait_faces.py` 对照，不撞脸才接入剧集。

## 5. 交付

- 向用户汇报：MP4 路径、时长、`review.md` 审稿单路径、做过的史实取舍、新入库的地点、ASR 有疑问的句子。
- 不要说"已验收"：读音、节奏和观感由用户最终判断。
- 在 HANDOFF.md 的"待办 4"里更新本集状态，例如"第 3 集已出片 `sanguo-03/M1`，XX 秒"。
- 新增的文件运行 `python 00_管理/tools/inventory.py` 刷新用途记录。

## 6. 边界

- **默认只写 `episode.yaml` 和地名库**。不要改引擎：`studio.py`、`territory.py`、`remotion-shuihong/src/studio/` 都不动。如果缺少组件或发现 bug，写进 HANDOFF.md 待办，告诉用户，等确认后再改；改引擎后要重跑 `projects/zz-*` 演示，确认没有破坏旧效果。
- 立绘按 `~/.codex/skills/history-portrait` 生成：透明 PNG，1024×1536，放 `03_素材/人物立绘/<id>.png`。缺立绘时用文字人物卡，不编造人脸。
- 红线：
  - 配音用 MiMo 内置音色白桦（voice skill 第八节）；不克隆任何真人的声音（周涛、白虹说等）；
  - 成片只用可商用数据（ETOPO、Natural Earth、Wikidata CC0、正史原文），CHGIS 和谭图只用于内部核对；
  - 不编造疆界、原文和对白；
  - 演义情节要明说"小说里……，史书上……"；
  - 不绕过验证码；下载大文件前先问用户；不改系统设置。

## 7. 常见坑（已踩过）

- "讨董"会被读成"陶董"，要说"讨伐董卓"。其他读错的字见 voice skill 第五节。
- 局部战役用区域比例尺（scale 约 9000）。在全国图上，行军队列会小得看不见。
- 校验器会把"几乎""韩遂"这类词误报成文言，白名单在 studio.py 的 lint 里，看到这类提示忽略即可。
- 镜头不要超出 `map.extent`，否则会露出底图边缘。extent 要比镜头最远处宽 3–5 度。
- 同屏元素不超过 4 个，旗牌要用 `until` 让它退场。
- 手绘素材在 `03_素材/动画素材/第N批/`，构建时自动缩到 1024 像素放进 `public/anim/`。新增素材按同样规格（透明 PNG、不带文字）放进新的批次文件夹即可，不用改构建脚本。
- 登基、驾崩、处斩等动作已经有专门的 `act`，不要再用单字 `stamp` 代替。
