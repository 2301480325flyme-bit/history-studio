# History Studio 脚本格式（episode.yaml v1）

一集 = 一个 YAML 文件，放在 `01_工作流/projects/<id>/episode.yaml`。
脚本只写**讲什么、在哪里、何时出现**；坐标、配色、字体、版式和动画全部由 Studio 提供。
同一套引擎渲染所有朝代，换一集只换脚本。

完整样例：
- [studio-qijiong-301](../projects/studio-qijiong-301/episode.yaml)：齐王冏起兵，导入了 ZTX-A1 的冻结配音。
- [studio-zhuwang-301](../projects/studio-zhuwang-301/episode.yaml)：诸王出镇，从零写成。

## 核心思路：以"拍"为时间单位

`beats` 中每一项对应一句旁白（`say`）。配音生成后，Studio 实测每句的起止时间，再把这一拍里的镜头、旗牌、箭头、字幕自动对齐到语音上。
所以**脚本里几乎不写秒数**。改了某句话，重新 build 就会自动重排；不必手调后面的所有时间。

## 顶层字段

| 字段 | 说明 |
|---|---|
| `id` | 唯一片 ID，用于输出目录 `05_项目/Remotion/studio/<id>/<build>/` |
| `title` / `series` | 左上片名和栏目行 |
| `year` | 叙事年份。用来从 maindata 选该年的古名（如建邺/建康）和城池等级 |
| `tail` / `duration` | 末句后的留白秒数（默认 1.2），或强制总时长下限 |
| `map` | 见下文 |
| `voice` | 见下文 |
| `places` | 本集用到的地点，见下文 |
| `regions` | 可选的有来源疆域面，见下文 |
| `camera` | 开场镜头：`focus`、`zoom`、`shift` |
| `beats` | 分拍旁白与画面 |
| `sources_local` | maindata `citations.json` 之外的本集来源：`[{id, work, volume, url}]`；`volume` 写成"卷一·武帝纪"的格式，底注会自动压缩成"卷一、九" |
| `notes` | 史实说明列表：演义与正史的差别、争议、取舍、编者概括。写进审稿单 |
| `factions` | 阵营配色，如 `{联军: red, 董卓: black}`；旗牌用 `faction:` 指定 |
| `auto_camera` | 默认 `true`：没写 `camera` 的拍，镜头自动跟随本拍涉及的地点 |
| `footer` / `theme` | 可覆盖自动生成的底注、图例和配色（一般不需要） |

### map

```yaml
map:
  center: [111.5, 34.0]       # 投影中心（墨卡托）
  scale: 12000                # 世界像素/弧度；全国 ~4000，中原 ~9000–12000
  extent: [100, 27, 124, 42]  # 底图范围 西,南,东,北
  basemap: relief             # relief（本地缓存晕渲瓦片）| none
  rivers: true                # Natural Earth 现代河网
  raster_res: 1.0             # >1 底图更清晰，文件更大（z9 瓦片约支持到 1.7）
  tone: {saturation: 0.28, contrast: 1.1, tint: '#d8bda0', tint_mix: 0.22}
  watermark: 西晋             # 左侧竖排大字
```

build 时会抽查整条镜头路径。只要任意时刻视野超出 `extent`，就报错，不会露出底图边缘。
`extent` 里没有本地瓦片的部分会以纸色填充，并给出百分比警告。

### voice

| mode | 用途 |
|---|---|
| `placeholder` | 按字数估时（0.24 秒/字），无声。用于排版和审镜头 |
| `mimo` | 调用 `mimo_tts.py` 逐句合成。`provider: preset | clone | design`，参数分别是 `voice` / `reference` / `description`；每拍可用 `style` 指导语气。结果按文本哈希缓存在 `projects/<id>/voice/`，改哪句只重合成哪句 |
| `files` | 每拍写 `audio: 路径`，使用已授权的录音 |
| `imported` | `mix: 混音.wav` + `timing: 分段时间.json`，直接复用旧构建的冻结音频 |

其他参数：
- `lead`：片头静默，默认 0.3 秒。
- `gap`：句间停顿，默认 0.18 秒；单拍可用 `pause` 覆盖。
- `bed: original | none | 文件路径`：`original` 是本机合成的原创持续音，并在每拍开头加一记低鼓。
- `bed_db`：声音床电平，默认 -18 dB；有人声时声音床会自动压低。

旁白的读音和混音好坏，Studio 无法替你判断，必须真人试听。

### places

```yaml
places:
  洛阳: {id: luoyang_han_wei, detail: 汉魏城址附近·近似点, label: left}
  邺: {id: ye_city, name: 邺城}
  荥阳: {lon: 113.38, lat: 34.79, precision: 现代市区近似点, source: https://…}
```

- 键名是脚本内部使用的简称；`id` 可以写 maindata 的地点 id，也可以写别名。
- 查不到就**报错**，不会猜坐标。新地点应补进 maindata。只用一次的地点可以就地写 `lon/lat/precision/source`，四项缺一不可。
- 下列字段会自动从 maindata 取值，也可以手动覆盖：
  - `name`：按 `year` 取当年古名。
  - `tier`：capital | city | stronghold | pass | region。`region_*` 地点会显示成大号州名。
- `label`：标签方位，可写 right | left | above | below，或 `[dx, dy]`。
- `detail`：小字说明。近似坐标会自动标"近似点"；写 `false` 可隐藏。
- `show`：默认 `always`。`false` 表示不显示城点，只能被元素引用；`"beat 3"` 表示从第 3 拍开始出现。
- 坐标未经策展的地点（如 `UNVERIFIED`）会给出警告。

### regions（可选）

```yaml
regions:
  - {id: jin, file: jin-300.geojson, name: 晋, fill: '#c99a6a', edge: '#8a5a2a',
     source: historical-basemaps world_300, precision: BORDERPRECISION=1 示意}
```

`source` 和 `precision` 必填，没有来源的边界不能上图。精度说明会自动写进片底。

**多政权快照**（一个 GeoJSON 里包含多个政权）：

```yaml
regions:
  - id: dj327
    file: ../../../02_数据/历史疆域/第二期/东晋(公元327年).geojson
    name_field: LABEL_CHN        # 按此字段分组，同名要素合并为一个政权
    main: 东晋                   # 主政权用柔和色、标签放大
    rename: {仇池: 仇池国, 某: '-'}   # 可选：改名；'-' 表示丢弃
    slots: {后赵: rose}          # 可选：钉死某政权的色位（跨集保持一致）
    labels: true                 # 政权名胶囊标签（毛笔字）
    show: always                 # 默认整集显示；false 则在 beat 里用 region: {id: dj327} 或 {id: dj327/后赵}
    source: …
    precision: …
    license: …                   # 商用前必须确认
```

- **颜色**：由 `palette.py` 生成。16 个色位在 OKLCH 空间里亮度统一，可在 `data/palette.json` 查看。按邻接关系自动分色：相邻政权会取最不易混淆的颜色，同时考虑红绿色盲。
- **渲染**：色块用正片叠底叠在地形上；繁体政权名自动转为简体。

### territory：势力范围时间轴（推荐用于割据题材）

按"哪个势力占有哪些州、郡"描述局势，不需要自己画边界。Studio 会自动完成：
- 逐郡染色，从势力中心向外扩散，易手时闪一下；
- 描出势力外轮廓；
- 放置势力名标签；
- 显示大字州名，推近时显示小字郡名。

```yaml
territory:
  cells: han-140                 # 郡格子：东汉郡国志 105 郡（data/cells/）
  zhou_labels: true
  jun_labels: always             # always＝郡名常驻（参考片的满屏地名）；true＝推近才显示
  polities:
    曹操: {slot: salmon, label_at: 许, main: true}   # 色位见 palette.json；label_at 为都城
    袁绍: {slot: sky, label_at: 邺}

beats:
  - say: …
    owners:                      # 从这一拍开始的完整局势
      袁绍: [冀州, 青州, 幽州, 并州]
      曹操: [兖州, 豫州, 徐州, 河南尹, 南阳郡]
      公孙度: [辽东郡, 玄菟郡]    # 点名到郡的优先于整州
    uncertain: [南阳郡]          # 斜纹：归属不明 / 示意
```

- 繁体、简体名称都能识别。查不到的州郡名、同一个郡被两个势力点名，都会直接报错。
- 相同局势要在多拍中保持时，可以用 YAML 锚点：第一次写 `owners: &s200`，后面写 `owners: *s200`。
- 每拍的 `sources` 和 `quote` 就是这一局势的依据，会写进审稿单。
- 新时代的郡格子用 `cells.py` 生成，方法见 `data/README.md`。

### 底图 `map.basemap: dem`（推荐，可商用）

用 NOAA ETOPO 2022 高程自制多方向光照晕渲，用 Natural Earth 分海陆、画湖泊和河网。效果是浅灰陆地、深灰蓝海洋，接近参考片。
- `river_rank`：控制河网密度，默认 6，数值越小越精简。
- `style`：可覆盖配色和光照强度，参数见 `basemap_dem.STYLE`。
- 旧的 `relief` 用的是 Esri 缓存瓦片，只能内部预览。

## beats：每一拍

```yaml
- say: 三月，齐王冏起兵，屯于阳翟。      # 旁白原文（配音用）
  caption: 三月，齐王冏起兵，屯于阳翟    # 字幕，≤18 字；省略时用 say 去掉句号
  phase: 三月 · 阳翟起兵                  # 右上阶段标；沿用到下次修改
  year: 301年                             # 左下年份牌；沿用到下次修改
  highlight: [阳翟]                       # 本拍高亮的城池（红点+光晕+显示详注）
  sources: [jinshu-004, jinshu-059]       # 必填；须在 citations.json 或 sources_local
  quote: 齐王冏起兵……屯阳翟。               # 对应原文摘句，进审稿单与旁白并排
  pause: 0.4                              # 本拍前的停顿（覆盖 voice.gap）
  camera: {focus: 阳翟, zoom: 2.5, shift: [0, 30], move: 3.0, delay: 0}
  show: [ ... 元素 ... ]
```

**camera**：
- `focus` 可以是一个地点，也可以是一组地点（取包围盒中心）。
- `zoom` 可写数字；对一组地点可写 `fit`，自动取景。
- `shift: [x, y]` 把焦点在屏幕上平移若干像素，用来给旗牌留位置。
- `move` 是推拉时长，`delay` 是相对本拍开始的延迟。
- 推拉用缓入缓出，缩放按对数插值，听感和观感都更匀。
- 不写 `camera` 时自动取景：
  - 本拍只涉及一个地点：推近到 `map.focus_zoom`（默认 2.0）。
  - 涉及多个地点：用 `fit` 把它们都框进画面。
  - 地点与上一拍相同：镜头不动。

## show：画面元素

每个元素写成 `- 类型: {参数}`。所有元素都支持三个计时参数：
- `delay`：相对本拍**语音起点**的延迟秒数。
- `for`：持续秒数。
- `until`：`beat`（默认，到本拍结束）、`beat+N`（到后面第 N 拍结束）或 `end`。

| 类型 | 参数 | 画面 |
|---|---|---|
| `flag` | `at` 地点, `name`, `sub`, `faction` 或 `color`(red/blue/green/purple/gold/gray/black/#hex), `side`(right/left), `note` | 竖旗人物/军队牌，蓝虚线连到城点。出场时自动选一个不和其他旗牌重叠的位置，之后保持不动；城点出画时自动淡出 |
| `arrow` | `from`, `to`, `via: [..]`, `kind`, `label`, `grow` 秒, `stop`(at/near/approach), `bend` | 红色发光箭头逐步生长 |
| `battle` | `at`, `text`, `title`, `side` | 战事脉冲圈 + 交叉标 + 战况牌 |
| `stamp` | `at`, `text`（诛/卒/篡/降…） | 红色印章盖下 |
| `card` | `title`, `body`, `at`(可选), `side` | 说明卡；不写 `at` 时放在左上 |
| `portrait` | `person`(maindata persons id) 或 `image`，或只写 `name` + `title` | 地图压暗，人物切入。有图时显示肖像，并注明"AI人物示意像"；没有图时显示竖排印章式的文字人物卡，不编造人脸 |
| `headline` | `text`, `sub` | 屏幕中央大标题 |
| `enter` | `who`, `at`, `side`, `title`, `role` | 人物立绘入场：淡入上浮、竖排题签，名字和封号·身份分两行出现，虚线连到据点 |
| `person_card` | `who`, `base`, `side` | 轻量人物卡滑入：头像、姓名、身份、据点、阵营色 |
| `versus` | `left`, `right`, `label`, `text` | 双人物对峙卡，中间落字印 |
| `exit` | `who`, `at`, `verb`, `portrait` | 退场：同名旗牌下沉变灰，落"诛 / 卒 / 败 / 囚 / 亡 / 奔 / 废 / 降"印，可选立绘变灰淡出 |
| `title_bar` | `text`, `sub` | 事件标题条，顶部居中滑入、停留后淡出 |
| `quote` | `text`, `source`, `era`, `side` | 史料引文卡（米色纸纹，角标标出处） |
| `faction_bar` | `text`, `faction` | 阵营提示条，左上角阵营色短条，可叠放 |

**第二批（地图动作）**：

| 类型 | 参数 | 画面 |
|---|---|---|
| `march` | `from`, `via`, `to`, `faction` | 标准行军箭头（到达后箭头脉冲、终点光圈），即 arrow 加阵营配色 |
| `multi_march` | `to`, `routes: [{from, via, faction}]`, `label`, `stagger` | 多路同时进军 |
| `flee` | `from`, `via`, `to`, `label` | 逃亡 / 败退：蓝色细箭头，尾部断续 |
| `siege` | `at`, `text`(围/攻/急), `faction` | 围城：收紧的旋转虚线环加字牌 |
| `capture` | `at`, `faction`, `text` | 易手：城点闪光并换色，挂"易手"牌 |
| `alliance` | `from: [地点]`, `at`, `text` | 会盟：多点连线汇聚，加字牌 |
| `replay` | `path: [地点…]`, `label` | 路线回放：发光轨迹加移动光点 |
| `spot` | `at`, `text` | 地点高亮：脉冲光圈加大字 |
| `breathe` | `faction` | 势力呼吸：该势力疆域明暗起伏（需要 territory） |

**第三批（军队与复合叙事动作，2026-10-07）**：一行脚本展开成一整段联动的地图、城池、人物和镜头。

| 类型 | 参数 | 画面 |
|---|---|---|
| `army` | `from`, `via`, `to`, `faction`, `banner`(旗上的字), `troops`(cavalry/infantry), `size`(人数级别，默认 3), `arrive`(台词关键词：说到这个词时恰好到达), `follow`(true 或倍数：镜头跟随) | 行军队列：阵营色大旗在前，小骑兵或步兵成纵队跟着箭头走，扬起尘土；到达后停留约 1.5 秒，随本句结束而退场（要多留就写 `until: beat+1`） |
| `army` 的部队参数 | `head`(将领：队首换成他的圆头像), `unit`(部队名), `merge: [人名]`(到达时合兵), `camp: false`(不扎营), `camp_offset: [x, y]` | 见下文「行军与驻扎」 |
| `chase` | `from`, `to`, `leader`(被追的人), `pursuer`(追的人), `faction`, `lag`(追兵落后多少，默认 0.12), `follow`, `merge` | 追击：两人的圆头像沿同一条路走，追兵逐渐逼近，贴近时出现光圈和刀光火花；算作 leader 大营的一次移动 |
| `camp` | `at`, `unit` 或 `head`, `faction`, `text`, `until`, `offset` | 营地：帐篷 + 名字，一直留到部队离开；有 `unit` 时参与部队时间线 |
| `vignette` | `image`(illus_* 文件名，不带扩展名), `cue`, `for`, `text`, `pos`(center/left/right), `zoom`(推近倍数，默认 1.08) | 情景插画窗：羽化椭圆窗口里的插画缓慢推近，窗外地图压暗但继续动；插画按原尺寸、不模糊放进构建 |
| `campaign` | `at`(战场), `sides: [{from, faction, banner, troops, size}, …]`(两方), `clash`(相撞时的台词关键词), `title`, 可选 `loser` + `rout_cue` + `retreat` | 集结—交战：两路行军队列同时出发，说到 `clash` 时正好在战场相撞（震屏、镜头推近、刀光烟尘、双方旗号），战后在原地留下小战痕 |
| `rout` | `at`(战场), `to`(退往), `faction`(败方), `banner`, `troops`, `cue` | 溃退：与同一战场的交战联动，败方倒地、变淡、后撤，残兵拖着歪斜的旗散乱逃走；败退路线随本句结束而退场 |
| `takeover` | `at`, `from`(原控制者), `to`(新控制者), `cue`, `gain: [州/郡]`(有史据才写), `sub`, `context` | 一城易手：镜头推近 → 原旗下沉变灰 → 城点闪烁变色挂"易手" → 新颜色从这座城向外晕染 → 新旗升起 → 镜头回拉交代新格局 |
| `defect` | `who`, `at`, `to`(新归属), `joins`(新主的据点), `cue`, `text`(连线标签), `verb`(归/降/叛/让/奔), `sub`, `gain` | 归附 / 倒戈 / 分裂：连线指向新主 → 旗牌翻牌变成新颜色 → 落字印 → 有史据的郡从此城晕染改色；原势力标签自动退出 |
| `yearshift` | `to`(新年份), `cue`, `ghost`(旧边界淡影秒数，默认 6) | 年份变化、地图保留记忆：镜头不动，顶部大年份牌翻页，年号牌同步翻；新格局铺开，旧边界留作虚线淡影、旧势力名留作空心标签，然后淡出。新 `owners` 写在同一拍 |
| `meanwhile` | `from`, `to`, `text`(如"与此同时"), `faction`, `spot`, `flag: {name, sub, faction}` | 视线交接：一条关系线从当前地点伸向另一地，镜头沿线平移，目的地亮起，旗牌入场 |
| `enter` 加 `settle: true` | `settle_sub`, `settle_until` | 立绘收成旗牌：人物介绍结束时，立绘缩小并飞到驻地，变成同名旗牌；随后可直接从这座城出兵 |

### 行军与驻扎：部队时间线（2026-10-19）

观众要能随时看懂「谁在哪」。写了将领名的部队，引擎会按时间顺序推算它的位置，不会凭空出现或消失：

- **给部队写名字**：`army` 上写 `head: 曹操`（队首挂将领头像），或 `unit: 关中军`（没有头像的部队名）。没写名字的部队只在行军时出现，`check` 会提示。
- **到哪扎营**：部队到达后自动在终点扎营（帐篷 + 名字），直到它下一次出发；出发那一刻营地消失。路线留一条淡虚线，标「曹操自洛阳而来」，直到它再次出发。
- **对峙分营**：两个营同时驻在一处时自动分开，各自靠向来的方向（马超自长安来在西侧，曹操自洛阳来在东侧）。要手动指定写 `camp_offset: [x, y]`（屏幕像素）。
- **分兵**：从大营所在地出发、写了另一员将领的 `army`（如 `head: 徐晃`），就是分出去的一支，大营不受影响。
- **合兵**：到达时写 `merge: [徐晃]`，徐晃营当场并入，只剩一个营，仍标「曹操」；之后整支一起行动。并入的将领再次出发，就重新成为分兵。
- **亲自渡河 / 被追**：`chase: {from, to, leader: 曹操, pursuer: 马超, merge: [...]}` 也算曹操大营的一次移动。
- **溃散**：`rout` 上写 `head: 马超`，他的营当场结束，留下「马超败走金城」的路线。`campaign` 的 `sides` 里也可以写 `head`，会传给行军和溃退。
- **奔赴战场**：`campaign` 的行军是 `stop: approach`，到了战场不扎营。
- **原本就驻在某地**：`camp: {at: 潼关, unit: 马超, faction: …, cue: …}` 表示一开始就在那里。
- **不想扎营**：`army` 上写 `camp: false`。
- **进城不搭帐篷（2026-10-24，第12批）**：部队到达的是一座城（都城、州治、郡治、县城、据点），而且这座城归他这一方（或归属未定），就不画帐篷，在城图标右上挂将领圆头像和「守」字，几支部队就并排几个头像。到达敌方的城（围城）仍在城外扎营。
- **帐篷只在战役特写里出现**：关隘、渡口、山头这类野外驻扎，在全国、数州的大视角里不画帐篷（屏幕上每公里不到 2.2 像素时隐藏），镜头推近到战区才出现。

### 城邑等级（2026-10-24，第12批）

城点按地点库（`data/gazetteer.json`，第12批考证）在**每一拍的故事日期**取等级，画成对应的图标：都城、州治、郡治、县城、据点、关隘、津渡。山、谷、原、战场、陵墓（region）只写名字。图标颜色按此刻这座城归谁来染。主公驻地（刘备称帝前的成都、曹操的邺、孙权称帝前的武昌等）在图标左上加一面双旗附标。
- 故事日期：本拍或之前最近的 `map: YYYY-MM`，没有就用最近的 `year:`。都城在一年里变动的（武昌 229 年四月到九月）按月份切换。
- 脚本里的 `places: {X: {tier: …}}` 只对还没考证过的地点生效；已考证的以地点库为准，`check` 会提示冲突。确实要改，去改 gazetteer，并写上依据。

`check` 会报这些问题：部队从一个它此刻不在的地方出发；没有行军就换了地方；已经溃散又出现；合兵时对方不在场；同一方的两个营同时驻在一处（是否该合兵）；部队没写名字。

另外两项自动行为：镜头推近到战区尺度（缩放 ≥ 2.3）时，右下角出现全图小地图，红框标出当前位置（`map.minimap: false` 关闭）；交战结束后战场留下小战痕约 14 秒（`trace` 可改，写 `end` 保留到片尾）。

**比例尺**：局部战役（几百公里内）要用区域底图，`map.scale` 约 9000、`extent` 只框相关几个州；全国底图（3500）上兵力队列会挤成一团。

镜头关键帧的 `zoom` 可以写相对值，例如 `x1.35` 表示在当前缩放上再推近 1.35 倍。

用 `cue` 对时且没写 `for` 或 `until` 的元素，至少保留 2.4 秒；关键词落在句尾时，会延续到下一拍。自动取景（`zoom: fit` 和自动镜头）最多推近到 3.2 倍。

人物用顶层 `people:` 统一声明，写法见 history-storyboard skill。拍上写 `year: 301` 这样的数字年份，会自动显示年号牌（永宁元年 / 公元301年）；同年改元时可以用 `era:` 覆盖。

**多国并立时的纪年**：默认按汉 → 魏 → 晋的正统序列（与《资治通鉴》一致）。顶层写 `era_dynasty: 蜀`（或 魏 / 吴 / 汉 / 晋），或在单拍上写 `era_dynasty: 吴`，就改按该国纪年，例如 234 年会显示蜀"建兴十二年"或吴"嘉禾三年"。年号表在 `maindata/chronology.json`，目前覆盖东汉光和至东晋。
| `region` | `id`（须在顶层 regions 中声明） | 疆域面淡入 |

### 箭头的三种性质（史实约束）

| kind | 含义 | 画法 | 要求 |
|---|---|---|---|
| `recorded` | 史料明载的行动路线 | 红实线 | 必须写 `evidence: {sources: [...], note: 原文所载}`，否则编译报错 |
| `direction` | 叙事方向示意（默认） | 红虚线 | 标签自动加"· 示意" |
| `relation` | 人物/地点关系 | 蓝细虚线，无箭头 | — |

图例会根据实际用到的元素自动生成。

## 让画面对准台词（cue）

- **元素**：`cue: 关键词`。元素在旁白说到这个词时出现（按字数比例估算时间，误差通常不超过 0.3 秒）。可以和 `delay` 叠加使用。
- **镜头**：`camera: {..., cue: 地名}`，会提前 0.3 秒开始移动。
- **局势变化**：在拍上写 `owners_cue: 攻占`。
- **字幕**：默认按分句自动切成 6–16 字一条，汉字年份自动转成数字（"一百九十年"显示为"190年"）。想手写字幕时用列表：`caption: [第一条, 第二条]`。顶层写 `captions: whole` 则恢复为整句字幕。

## 配音的语气与语速

- `voice.style`：全局语气提示，例如"语速偏快，节奏紧凑，像短视频里讲历史故事"。实测能把语速从 3.1 提到 5.9 字/秒。
- 每拍 `style`：覆盖全局语气，用于钩子、转折、收束等关键拍。
- `voice.speed` 或每拍 `speed`：保持音调的变速，建议 1.05–1.2。
- 详见 `.claude/skills/history-voice/SKILL.md`。

## Agent 工具

| 命令 | 用途 |
|---|---|
| `studio.py sources 词1 词2 --books 三国志 后汉书` | 检索本地二十四史，返回段落 ID、卷题和原文片段；结果会标出 OCR 缺字 |
| `studio.py places 名1 名2 --year 190 --web` | 先查本地库（maindata + 共享地名库），查不到再查 Wikidata 候选（只保留带坐标的） |
| `studio.py place-add --id … --name … --lon … --lat … --precision … --source … --years=190-220` | 把确认过的地点写入 `data/gazetteer.json`，后续各集共用；标记为待人工复核 |
| `studio.py check <yaml> --json` | 机器可读的校验结果，供 Agent 自动修正 |
| `studio.py still <yaml>` | 默认在每拍语音中点各抽一帧，并拼成 `stills-sheet.jpg` |

`voice.mode: mimo` 时，每句配音生成后都会用 MiMo ASR 听写一遍，再与原稿逐字比对，生成 `voice/asr-report.md`。一致度低于 0.92 的句子会给出警告。

每次构建都会生成 `review.md`，作为给人看的审稿单，内容包括：
- 史实说明；
- 逐拍旁白与出处、原文对照；
- 地点精度及其入库状态；
- 箭头性质；
- ASR 校对结果；
- 警告。

## 自动完成的事

- 字幕按实测语音起止显示（前后各留 2 帧）。
- 城池标签自动避让：先排高亮城，再排都城，最后其他城；放不下时先隐藏详注，再隐藏名字。
- 底注左侧自动写入精度声明，右侧自动列出本集用到的史书卷次和底图署名。
- `build.json` 记录每个地点的来源与精度、用到的来源、配音测量方式、混音电平、底图瓦片和所有警告，供审查使用。
