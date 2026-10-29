# 部署说明

这个仓库只放代码和文本：引擎（`01_工作流/history-studio`、`01_工作流/remotion-shuihong/src`）、剧本（`01_工作流/projects`）、系列数据（`01_工作流/series`）、规范（`.claude/skills`、`AGENTS.md`）。

字体、立绘、动画素材、音效、配乐、配音缓存、底图、史书语料、构建和成片都不在 git 里，放在 Google Drive，用 rclone 按需拉取。

密钥 `MIMO_API_KEY`、`MINIMAX_API`、`GEMINI_API` 只设成环境变量，不写进任何文件。

## 从 Google Drive 拉媒体（Linux / Grok Bot）

媒体包在 Google Drive「我的云端硬盘/HistoryStudio-media/」，目录结构和本仓库一致，拉下来直接叠在仓库上。

```bash
# 1. 安装 rclone，配置一次 Google Drive（远程名用 gdrive；无头机器按提示用 rclone authorize 在有浏览器的电脑上授权）
curl https://rclone.org/install.sh | sudo bash
rclone config

# 2. 第 1 批：构建必需（字体、底图和高程缓存、Remotion 公共资源、素材库、第 18–43 集配音缓存）
cd /workspace/history-studio
rclone copy "gdrive:HistoryStudio-media/01_工作流" "01_工作流" --progress
rclone copy "gdrive:HistoryStudio-media/03_素材" "03_素材" --progress

# 3. 第 2 批：查史料时再拉（史书语料）
rclone copy "gdrive:HistoryStudio-media/02_数据" "02_数据" --progress
```

不传：第 1–17 集配音缓存（已发布，不再构建）、`05_项目` 构建和成片、`04_参考`、`07_其他博主视频案例`。
