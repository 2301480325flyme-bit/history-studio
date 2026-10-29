# 城池库：使用与补录

当前：5处候选城址、2条已核原文的军镇记录；尚无完整实际控制权、行政隶属或疆界数据库。

## 直接使用

从 `D:\history\codx_3 history studio\01_工作流` 执行：

```powershell
$env:PYTHONIOENCODING='utf-8'
python studio_catalog.py validate
python studio_catalog.py lookup 邺城 --year 301 --snapshot 301-before-uprising
python studio_catalog.py lookup 洛阳 --year 301
python studio_catalog.py export --places luoyang_han_wei ye_city --year 301 --technical-preview --output projects/geolayers-p0/places.geojson
```

第一个查询会返回司马颖军镇邺城的记录；实际控制权、行政隶属等无已核记录的关系仍返回 `unknown`。去掉 snapshot，不会把起兵前的军镇状态延长为整年状态。已知古名与指定年份不符时拒绝查询，例如 `建康 --year 300`。

## 当前两条记录的依据

- [《晋书》卷五十九·齐王冏传](https://zh.wikisource.org/wiki/晉書/卷059#齊武閔王冏)：核到司马冏军镇许昌、举兵后屯阳翟。许昌现代近似坐标仍待核；文本事实与坐标精度分别审核。
- [《晋书》卷五十九·成都王颖传](https://zh.wikisource.org/wiki/晉書/卷059#成都王穎)：核到司马颖镇邺，并发兵响应司马冏。
- [《晋书》卷四·惠帝纪·永宁元年](https://zh.wikisource.org/zh-hant/晉書/卷004#永寧元年)：用于核对起兵、宫变的年内先后顺序。纪年与月序保留原历法，不直接伪造公历日。

`301-before-uprising` 是按传记顺序重建的叙事快照。它不是301年全年的连续行政控制记录。军镇表述也不表示本人在每一时刻都留在城中。现在两条关系的 `reviewed` 指本轮原文核对，未表示人类最终审校或坐标已通过。

## 后续新城如何补

1. 先查名字及别名：若城址迁移，建新的 place_id，不能只给老点改名。
2. 在 sources 添加书名、卷章、链接/本地文件页码、来源版本与核对范围。
3. 添加 names 的适用年份、来源、审核状态。
4. 添加 location：WGS84经纬度、点位含义、accuracy_m；城址中心、宫城和现代市中心须分别标明。SHP先看实际CRS再转换，不能单改CRS标签。
5. 分别添加行政上级、名义政权、实际控制、军镇、在场、封地关系。关系须有显式时间段或命名快照。
6. 用 validate 校验结构，lookup 查看有无未知或冲突，再核对地图点位。
7. names 与 location 都经审核后才允许正式GeoJSON导出；技术验证必须显式带 `--technical-preview`。

名字的年份区间含首尾；关系的时间段左闭右开。同名多个城址会拒绝自动择一。未知状态不得按政权疆域颜色自动填成已知控制权。

目前未接入CHGIS自动检索、史料自动抽取或控制事件批量推演；这三项需后续实现。校验器核对字段与引用存在性，史料真实性和内容仍需审阅。
