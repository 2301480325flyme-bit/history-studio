# History Studio（Remotion）

导入一份脚本，生成"地图推演"式历史视频。所有朝代共用同一套引擎、动画和版式。
目标风格参照 `04_参考/案例视频/地图推演 两晋南北朝 第一集…mp4` 的视听语法，具体包括：
- 晕渲底图和蓝色河网；
- 全景、战区间的推拉镜头；
- 竖旗人物牌和发光箭头；
- 暗底肖像切入；
- 左下年份牌，底部半透明字幕条。

这里只借用视听语法，不复制参考片的素材、文案或剪辑。

## 网页 Studio

双击项目根目录的 **`启动 History Studio.bat`**，或者运行 `python 01_工作流/history-studio/webui/server.py`，然后在浏览器打开 http://127.0.0.1:8770 。服务只在本机监听，局域网和外网都访问不到。

| 位置 | 用途 |
|---|---|
| 左侧「＋ 新建 / ⇪ 导入脚本」 | 从模板新建一集；或上传、粘贴 `episode.yaml`（Agent 写好的脚本也从这里导入） |
| 概览 | 本集统计、推荐步骤、最新构建的抽帧图 |
| 配置 | 用表单改片名、地图、镜头、配音、势力（色位与都城）、地点。保存时只改动过的条目，保留脚本注释，并自动备份到 `.history/` |
| 脚本 | YAML 编辑器（Ctrl+S 保存），右侧实时显示校验结果 |
| 分拍 | 逐拍总览：旁白、字幕、出处、原文、镜头、画面元素、局势；点一下跳到脚本对应位置 |
| 构建与渲染 | 校验、排版预览（无声构建并自动逐拍抽帧）、正式构建（配音加 ASR 校对）、渲染成片、实时预览（Remotion Studio 时间轴）。显示任务日志和进度；同一时间只跑一个渲染 |
| 成片 | 按构建切换：视频播放和下载、逐拍抽帧、全片抽帧、审稿单 |
| 资料工具 | 史料检索（本地二十四史，可复制原文）、地名查询（本地库加 Wikidata）、政权色板 |

代码在 `webui/server.py`（标准库 HTTP 服务加 ruamel.yaml）和 `webui/static/index.html`（单页，CodeMirror 和 marked 从 cdnjs 加载）。

## 一句话出片（推荐用法）

在本项目的 Claude Code 里直接说题目，例如"做十八路诸侯讨伐董卓"。Agent 会按 skill [`.claude/skills/history-video`](../../.claude/skills/history-video/SKILL.md) 自动完成以下步骤：
1. 检索本地二十四史和网络资料；
2. 写现代口语旁白，每句附原文出处；
3. 查询地点并写入共享地名库；
4. 输出 `episode.yaml`；
5. 校验、无声排版、逐拍抽帧自查；
6. MiMo 配音并做 ASR 听写校对；
7. 渲染成片。

最后交给你成片和 `review.md` 审稿单。你只需要审稿、试听、验收。

Studio 本身是"棋盘"：地图、地名库、动画、版式和校验规则都内置在里面。Agent 是"棋手"：只负责输出脚本。下面是棋盘的手动用法。

## 流程

```text
episode.yaml ──check──▶ 校验：地名查库 / 出处必填 / 箭头性质 / 时间
     │
     ├─voice──▶ 逐句配音（MiMo / 录音 / 导入），实测每句起止
     │
     └─build──▶ 05_项目/Remotion/studio/<id>/<build>/
                  public/episode.json   编译后的中间表示（坐标、时间全部算好）
                  public/relief.jpg     按投影拼接的本地晕渲底图
                  public/mix.wav        旁白 + 原创声音床（自动压低）
                  build.json            来源、精度、测量、警告的审查记录
          ──still / preview / render──▶ 单帧 / Remotion Studio 预览 / MP4 + media-check.json + contact-sheet.jpg
```

## 命令

在 `01_工作流/history-studio` 下运行：

```powershell
$env:PYTHONIOENCODING='utf-8'
python studio.py new my-episode                                  # 生成 projects/my-episode/episode.yaml
python studio.py check  ..\projects\my-episode\episode.yaml      # 只校验，不出文件
python studio.py build  ..\projects\my-episode\episode.yaml      # 生成构建（--build S1 指定编号；--voice placeholder 临时无声排版）
python studio.py still  ..\projects\my-episode\episode.yaml -t 3 8 15   # 抽帧审看
python studio.py preview ..\projects\my-episode\episode.yaml     # 打开 Remotion Studio 逐帧拖看
python studio.py render ..\projects\my-episode\episode.yaml      # 渲染最新构建
```

构建编号已存在时拒绝覆盖。构建失败会删除这次的半成品目录。脚本写法见 [SCRIPT.md](SCRIPT.md)。

## 代码位置

| 部分 | 位置 |
|---|---|
| 编译器 / CLI | `history-studio/studio.py` |
| 渲染引擎 | `remotion-shuihong/src/studio/`：`index.tsx` 入口，`Episode.tsx` 合成，`Marks.tsx` 地图标记，`Overlays.tsx` 版式，`anim.ts` 缓动/镜头/路径 |
| 公共素材 | `history-studio/assets/fonts`（思源宋/黑 SC，OFL），`history-studio/data/rivers-ne50.geojson`（Natural Earth，公有领域） |
| 数据来源 | `maindata/places.json`、`places_approximate.json`、`places_curated.json`、`persons.json`、`citations.json` |
| 底图缓存 | `.workbuddy/*_cache` 瓦片（z6 全国、z8/z9 中原）→ `history-studio/cache/`（可删，会自动重建） |

引擎只读取 `episode.json`，不含任何单集内容。旧的 `qijiong-*` 入口和冻结构建都没有改动。

## 地图底座（可商用，2026-10-07）

| 部分 | 实现 |
|---|---|
| 底图 | `basemap_dem.py`：NOAA ETOPO 2022 高程算多方向光照晕渲，Natural Earth 分海陆、湖泊、河网。效果是浅灰陆地、深灰蓝海洋，全部为公有领域数据 |
| 政权色 | `palette.py`：OKLCH 空间生成 16 个色位，按邻接关系分色，并做色盲检查 |
| 字体 | 马善政毛笔楷书（标题、旗牌、政权名）加思源宋体/黑体，均为 OFL，见 `assets/fonts/FONTS.md` |
| 郡格子 | 郡国志结构（`parse_junguozhi.py`）+ Wikidata 坐标（`fetch_han_wikidata.py`、`fetch_modern_seats.py`、`match_han.py`）+ 地形代价扩张（`cells.py`），生成 `data/cells/han-140` |
| 势力时间轴 | `territory.py` 加引擎的 `Territory.tsx`：逐郡染色扩散、势力轮廓、都城标签、州名和郡名、斜纹表示不确定 |

试片：`05_项目/Remotion/studio/geyu-200/S2`，《官渡之前·群雄割据（200 年）》，64 秒，MiMo 配音，ASR 8/8 句一致。

## 已验证

- `studio-qijiong-301/S3`：用脚本复现了冻结的 QJ-ZTX-A1，导入原混音。26 秒，1080p30，全片解码通过，-22.5 dB 均值 / -6.5 dB 峰值。
- `studio-zhuwang-301/S2`：从零写的第二集，零代码改动。20.6 秒，无声排版版。
- 区域面、`recorded` 箭头的证据门槛、z6 底图兜底均经冒烟测试。引擎通过 TypeScript strict 检查。

以上仅是技术检查。史实、画面、读音和混音仍需人工审片和用户验收。

## 限制与待办

- **底图许可**：Esri 晕渲瓦片只能用于内部审看。公开或商业发布前，须换成许可清楚的底图（如自制 DEM 晕渲）。
- **底图覆盖**：z8/z9 只覆盖中原，其他地区只有 z6，较粗；`extent` 中无瓦片的部分以纸色填充，并在构建时报警。江南、关中以外地区要先补瓦片。
- **地点库**：maindata 只有 13 个正式地点和 28 个州级示意点。每做一集，都要先把地点补进 maindata。
- **疆域**：只有 300 年低精度晋域。没有可信来源的边界不能上图，这是有意的限制。
- **配音**：MiMo 需要 `MIMO_API_KEY`，且会把文本和参考音发送到服务端。读音和重音必须真人试听。
- **还没做的**：多集批量调度；与 runner/Agent Mail 的冻结-审查对接；剧本前端（史料 → episode.yaml 草稿）。
