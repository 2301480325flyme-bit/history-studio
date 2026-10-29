# maindata · 主表目录

全局唯一的数据主表。**各集脚本只引用这里的 id，不再重复写坐标 / 颜色 / 生平 / 出处。**

## 文件

| 文件 | 内容 | 生成方式 |
|---|---|---|
| `places.json` | 地名主表：别名、坐标、年代名称、等级时间线、冲突记录 | `build_maindata.py` 自动 |
| `persons.json` | 人物主表：别名归一、封地、肖像、跨集字段差异 | `build_maindata.py` 自动 |
| `powers.json` | 政权主表：生命周期、都城、配色 | 人工维护 |
| `chronology.json` | 纪年换算：干支 + 西晋/东晋年号表 | 人工维护 |
| `citations.json` | 史料引文库：史书卷次、地理数据、遗址考据 | 人工维护 |
| `reuse/eventSequence.json` | 事件序列模板（起兵/篡位/灭亡/北伐） | 人工维护 |
| `reuse/pacingProfile.json` | 节奏骨架（60s / 180s / 600s） | 人工维护 |
| `reuse/cameraPhrase.json` | 运镜句式（交代/战斗/对比/收尾/揭晓） | 人工维护 |
| `冲突报告.md` | ⚠️ 自动生成，记录所有冲突与数据质量问题 | `build_maindata.py` 自动 |

## 五个脚本

```bash
# 1. 从现有零散数据汇总主表（机械汇总，不手抄）
python build_maindata.py

# 2. 坐标统一 + 剥离为纯 id 引用
#    产出 *.resolved.json（坐标统一版）与 *.byid.json（不含坐标版）
python resolve_dynasty.py

# 3. 校验（集数据 + 资产自校验）
python maindata.py check              # 全量
python maindata.py check 八王之乱-起兵  # 单集
python maindata.py assets             # 只校验模板/纪年/引文/政权/tiers

# 4. 叙事模板 → 分镜骨架
python compile_story.py --template raise-and-march \
  --actor sima_jiong --from xuchang_approx --to luoyang_han_wei \
  --rival sima_lun --year 301 --pacing short-60 \
  --title "齐王冏起兵" --subtitle "许昌 → 洛阳" \
  --out "../../05_项目/生成/qi-wang-jiong.director.json"

# 5. 二十四史事件抽取
python extract_events.py scan 二十四史全译05.晋书.txt --top 30
python extract_events.py entities 二十四史全译05.晋书.txt
python extract_events.py extract 二十四史全译05.晋书.txt --range 纪第四 --out cand.json
```

## 查询工具

```bash
python maindata.py place 洛阳 301      # 地名（含年代 → 当时叫什么、什么等级）
python maindata.py person 东海王        # 人物（别名归一 → sima_yue）
python maindata.py power 晋 300        # 政权（含年代消歧）
python maindata.py ganzhi 301          # 干支换算
python maindata.py era 永康元年         # 年号换算
```

## 两条铁律

1. **每个实体只在一个地方定义。** 各集数据出现坐标 / 颜色 / 生平，即为冗余，应改为引用 id。
2. **冲突如实记录，绝不静默取舍。** 坐标冲突进 `coordinatesAlt`，字段差异进 `fieldVariants`，全部进 `冲突报告.md`。

## 当前已知问题

见 `冲突报告.md`。其中最需要人工判定的：

- **许昌坐标两处相差 15.34 km** —— 超出制图误差，必须人工判定。
- **司马攸 / 司马炽 / 司马乂 / 司马颙 四人的记载两集矛盾** —— 涉及史实，须回源核对。
- **`八王之乱-301/kings.json` 存在 U+FFFD 乱码** —— 写入时已丢字。
- 5 个地点（成皋/河内/温县/濮阳/阳翟）**只有单源坐标，无出处**。
