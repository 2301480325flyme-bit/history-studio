# 部署说明

这个仓库只放代码和文本：引擎（`01_工作流/history-studio`、`01_工作流/remotion-shuihong/src`）、剧本（`01_工作流/projects`）、系列数据（`01_工作流/series`）、规范（`.claude/skills`、`AGENTS.md`）。

字体、立绘、动画素材、音效、配乐、配音缓存、底图、史书语料、构建和成片都不在 git 里，放在 Google Drive，用 rclone 按需拉取。

密钥 `MIMO_API_KEY`、`MINIMAX_API`、`GEMINI_API` 只设成环境变量，不写进任何文件。
