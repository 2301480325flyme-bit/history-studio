# History Studio 工作约定

先读根目录 README.md 和 思路与方向.md。制作路线只有一条：**Remotion**（2026-10-10 起 AE / GEOlayers 路线和三角色协作系统已全部移除，旧报告里提到的 AE 状态不再适用）。

## 单集出片（《三国到隋》合集等）

用户说"做第 N 集 / 做某段历史的地图视频"时，读 `01_工作流/history-studio/CODEX-SOP.md` 并按它执行。
由单个代理完成；规范在 `.claude/skills/` 下（history-video / narration / storyboard / voice），立绘规范在 `~/.codex/skills/history-portrait`。

## Claude 主控 · Codex 辅助（2026-10-24 起）

- 分工、派活、验收全在 `01_工作流/history-studio/协作-Codex.md`。Claude 写大纲、旁白、分镜、引擎并验收；Codex 做史料包、考证、建档、生图和批量活。
- Claude 用 `python 01_工作流/history-studio/tools/codex_task.py start …` 派活，记录在 `00_管理/codex任务/`。
- **Codex 被派活时**：只写任务单允许的目录；不改引擎代码和 episode.yaml 的 beats；不渲染、不提交；读写中文用 Python（PowerShell 5.1 会乱码）；查不到的史料写「未核」；最后一条消息就是汇报。

## 立绘（2026-10-23 起）

- 不要把自己当生图工具：先读史料、写人物卡和《人物相貌档案》（`01_工作流/series/三国到隋/人物相貌.yaml`），再生图；每人 1 张，最多重画 2 次。
- 交付前必须运行 `python 01_工作流/history-studio/tools/portrait_faces.py --new … --near …`，遮住帽子道具只看脸，分不清就不交付。
- 详细规则见 `~/.codex/skills/history-portrait` 第二节之二和第八节。

## 通用约定

- **先预览、后渲染**：构建后在 Remotion 实时预览里给用户看，用户明确同意后才渲染。
- **以声音为主线**：时间轴由配音决定，不为凑时长或配合动画去提速、压缩停顿。
- 构建编号不覆盖（P1、P2…）；改引擎（`studio.py`、`territory.py`、`remotion-shuihong/src/studio/`）后重跑 `projects/zz-*` 演示，确认没有破坏旧效果。
- 新素材与工程保持分区：立绘在 `03_素材/人物立绘/`，手绘动画素材在 `03_素材/动画素材/第N批/`，音效在 `03_素材/音效/`，人物配音样本在 `03_素材/配音参考/人物/`。
- 新增文件后按 `python 00_管理/tools/inventory.py` 刷新用途记录。
- 密钥（`MIMO_API_KEY`、`MINIMAX_API`、`GEMINI_API`）只从环境变量读取，不打印、不写入文件。
- 视频验收需要史实、实际画面、运动、声音和工程证据；代码测试不等于成片验收。读音、节奏和观感由用户最终判断。
