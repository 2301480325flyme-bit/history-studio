# History Studio 数据

| 文件 | 内容 | 来源与许可 | 生成方式 |
|---|---|---|---|
| `palette.json` | 16 色位政权色板及自检结果 | 自制 | `palette.py` |
| `gazetteer.json` | 各集查证后入库的共享地点（带来源、精度、复核状态）；含三国数据包 45 处（`pack: sanguo`，由 `build_sanguo_places.py` 生成） | 各条单独注明（多为 Wikidata，CC0） | `studio.py place-add` |
| `wikisource/hhs-109…113.wiki` | 《后汉书》志第十九至二十三·郡国志原文 | 维基文库，公有领域文本 | `parse_junguozhi.py` 自动缓存 |
| `han-commanderies.json` | 东汉 13 州、105 郡国、1189 县，每郡首列县为治所 | 由上面的郡国志解析得到 | `parse_junguozhi.py` |
| `han-wikidata-candidates.json` | 按郡、县名精确匹配到的 Wikidata 条目 | Wikidata，CC0 | `fetch_han_wikidata.py` |
| `han-seats-modern.json` | 105 个郡治对应的今址（人工整理的历史地理常识） | 自制，属事实性对照 | 手工整理 |
| `han-seats-geocoded.json` | 郡治今址的坐标 | Wikidata 现代地名，CC0 | `fetch_modern_seats.py` |
| `han-county-coords.json` | 县治坐标（以郡治为锚点做了距离校验） | Wikidata，CC0 | `match_han.py` |
| `han-county-rejects.json` | 人工排除的同名误配县（如颍川阳城误配到山西阳城县），生成郡格子时跳过 | 自制 | 手工整理 |
| `han-counties-modern.json` | 县治 → 今县级驻地对照（约 750 县，2026-10-15 整理） | 自制，属事实性对照 | 手工整理 |
| （更新）`han-county-coords.json` | 上表经 Wikidata 取坐标后补入：县治定位由 263 提到 939/1189 | Wikidata，CC0 | `fetch_modern_counties.py` |
| `han-219-commanderies.json` / `han-219-county-coords.json` | 建安郡：140 年郡国 + 建安新设 29 郡（逐郡注出处），县按新郡重新归属 | 正史（公有领域）+ 上面数据 | `derive_219.py` |
| `cells/han-219.geojson` / `.npz` | 建安郡格子（133 郡）；每郡带 `parent`（所出 140 年郡），疆域.yaml 写原郡名时拆出的新郡同主则跟着走 | 同下 | `cells.py han-219` |
| `cells/han-140.geojson` / `.npz` | 东汉郡格子：105 个郡和 13 个州的面，以及栅格标签 | 由以上数据加 ETOPO、Natural Earth 推算 | `cells.py han-140` |
| `rivers-ne50.geojson` | Natural Earth 1:50m 河流（旧底图使用） | 公有领域 | — |

**城邑图层**：格子文件里的 `cities` 是全部已定位县治（郡治为 1 级、县治为 2 级，约 4 公里内重合的只留一个），片中常驻显示，位置为今址近似，示意用。

**郡格子的精度**：从郡治、县治出发，按地形代价做扩张：翻山、过大河代价高，海洋不可通行。郡界是推算出来的示意范围，不是考订的疆界。片中会自动注明"势力范围按郡示意，郡界为推算"。

**为什么不用 CHGIS 和谭图**：它们的许可只允许非商业使用，而视频要投放 TikTok。这两套数据只可以在内部用来人工核对，不进入成片。

**换一个时代时**，按同样的方法再建一套郡格子，例如用《晋书·地理志》《宋书·州郡志》作骨架，在 `cells.py` 的 `SETS` 里加一项即可。
