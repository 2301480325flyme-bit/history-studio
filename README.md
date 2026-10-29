# History Studio 工作区

主目录：`D:\history\codx_3 history studio`。用 Remotion 制作历史地图解说视频（横屏 16:9，中文，抖音）。
2026-10-10 起只保留 Remotion 路线：AE / GEOlayers 工程、教程和三角色协作系统已删除。

## 从这里开始

- [目前思路与方向](思路与方向.md)：当前系列、已定的决定、进度和下一步。
- [History Studio（Remotion）](01_工作流/history-studio/README.md)：写一份 `episode.yaml` 即可出片的地图视频引擎；[脚本格式](01_工作流/history-studio/SCRIPT.md)。双击 `启动 History Studio.bat` 打开网页工作台（构建、预览、渲染、音效试听）。
- [Codex 出片流程](01_工作流/history-studio/CODEX-SOP.md)和[交接文档](01_工作流/history-studio/HANDOFF.md)。
- [系列规格与分集大纲](01_工作流/series/三国到隋/README.md)。
- [逐文件用途说明](文件用途说明.md)、[文件用途清单 CSV](文件用途清单.csv)（由 `00_管理/tools/inventory.py` 生成）。
- [GitHub 版本管理](GITHUB.md)：仓库收录范围、Git LFS 和新电脑恢复说明。

## 功能分区

| 目录 | 放什么 |
|---|---|
| `01_工作流` | `history-studio`（编译器、配音、网页工作台）、`remotion-shuihong`（渲染引擎）、`projects`（各集 episode.yaml 与配音缓存）、`series`（系列旁白稿、故事稿）、`maindata`（人物、地名、史料语料） |
| `02_数据` | 历史疆域、行政区、CHGIS、谭图（只作内部核对，不出现在成片里）、史料原文 |
| `03_素材` | 人物立绘、手绘动画素材（第 1–3 批）、音效与原创合成音效、配音参考、字体 |
| `04_参考` | 白虹说节奏拆解、地图版式参考、案例视频 |
| `05_项目` | `Remotion/studio/<集>/<构建>`：每次构建的预览数据、配音混音和成片 |
| `06_报告` | 配音、音色、音效的试听页和实验记录 |
| `.workbuddy` | 底图地形瓦片（引擎直接读取，不要删） |

## 第 6 批人物立绘登记

立绘位于 `03_素材/人物立绘/`，均为系列示意图；相貌、服色及细节依人物卡标明史料边界。

| 档 | 人物 | 文件 |
|---|---|---|
| A | 郝昭、公孙渊、曹芳、桓范、蒋济、李胜、王凌、文钦、文鸯、贾充、陈泰 | `hao_zhao.png`、`gongsun_yuan.png`、`cao_fang.png`、`huan_fan.png`、`jiang_ji.png`、`li_sheng.png`、`wang_ling.png`、`wen_qin.png`、`wen_yang.png`、`jia_chong.png`、`chen_tai.png` |
| A | 成济、谯周、曹奂 | `cheng_ji.png`、`qiao_zhou.png`、`cao_huan.png` |
| B | 司马衷、贾南风、杨骏、卫瓘、司马攸、司马遹、司马亮、司马玮 | `sima_zhong.png`、`jia_nanfeng.png`、`yang_jun.png`、`wei_guan.png`、`sima_you.png`、`sima_yu.png`、`sima_liang.png`、`sima_wei.png` |
| C | 山涛、张华、裴頠、司马伦、司马冏、司马颖、司马颙、司马乂、司马越 | `shan_tao.png`、`zhang_hua.png`、`pei_wei.png`、`sima_lun.png`、`sima_jiong.png`、`sima_ying.png`、`sima_yong.png`、`sima_yi2.png`、`sima_yue.png` |

登记表中的 11 张 A 档图已由前一轮完成；成济与谯周沿用本轮开始前已存在的同名图。第 6 批材料与验收汇报见 `06_报告/codex-第6批立绘-汇报.md`。
