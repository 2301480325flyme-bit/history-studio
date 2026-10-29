# MiMo 旁白接入

小米 MiMo 的 `mimo-v2.5-tts-voicedesign` 可以从文字描述生成原创音色，不需要真人参考录音。本工作流将其输出为 WAV，再导入 AE 的 `NARRATION` 层，AE 负责画面、字幕、音频和最终渲染。[MiMo 官方语音合成文档](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)

## 历史讲述的语气

单靠“庄重、放慢”一类整片音色描述，容易把所有句子读成同一语调。历史讲述应由事件决定起伏：铺垫平稳，转折略抬，结果落下。先在旁白文字中写清因果和反转，再为每段指定一两处真正需要强调的词。

在导演 JSON 中使用原创预设声线和逐段指导：

```json
{
  "ttsProvider": "mimo-preset",
  "mimoVoice": "茉莉",
  "mimoStylePrompt": "像熟悉历史的人自然讲故事，语气随事件起伏。",
  "narrationSegments": [
    {
      "start": 0.7,
      "end": 13.8,
      "text": "司马亮被杀。可动手的司马玮，也很快被处死。",
      "stylePrompt": "前句沉稳；‘可’带出转折；后句落下，留一点意外感。"
    }
  ]
}
```

`stylePrompt` 覆盖该段的 `mimoStylePrompt`，省略时继承全局指导。`narrationSegments` 逐段合成并放入指定时间窗；若音频超时，需缩短文字或延长镜头。逐段生成仍可能有音量、音色和节奏差异，必须以试听判断。若 MiMo 无法达到目标，工作流也接受获准使用的录音作为 `narrationAudio`。

## 用获授权的参考音频复刻音色

在导演 JSON 中设置 `ttsProvider: "mimo-voiceclone"`、`mimoReferenceAudio` 和可选的 `mimoStylePrompt`；每个 `narrationSegments` 项可用 `stylePrompt` 单独指导语气，也可用 `referenceAudio` 换一段参考。参考音频须为 WAV 或 MP3，Base64 编码后不超过 10 MB。[MiMo 官方音色复刻接口说明](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)

本地案例见 [《中国》旁白参考记录](<../03_素材/配音参考/zhou-tao/VOICE_PROFILE.md>)和 [八王之乱 120 秒自然句法版导演稿](<examples/eight-princes-291-306-story-v5-natural-delivery.director.json>)。用户反馈逐词重音指令产生了不合句意的强调，因此 v5 去掉这些指令，先靠句法和标点形成自然起伏。当前参考来自纪录片混音，可能含配乐；判断音色和语气请先听短试听，再决定是否整片采用。MiMo 调用会把所选参考音频发送给服务端。

## API Key 放在哪里

1. 打开 [Xiaomi MiMo 控制台](https://platform.xiaomimimo.com/)，用小米账号登录，在 **API Keys** 页面新建普通 API Key（通常以 `sk-` 开头）。本工作流使用普通实时 API 的 `https://api.xiaomimimo.com/v1`，不是 Token Plan 专属地址。[官方首次调用说明](https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call)
2. Windows 开始菜单搜索“编辑系统环境变量”→“环境变量”→“用户变量”→“新建”。变量名填 `MIMO_API_KEY`，变量值填刚复制的 Key。关闭并重新打开 Codex 或 PowerShell，让新变量生效。
3. 在新的 PowerShell 窗口运行 `[bool]$env:MIMO_API_KEY`，显示 `True` 即已读取；不要打印密钥内容，也无需把密钥发到聊天里。
4. 运行 `run.py <导演稿> --out <输出目录> --aep-only`。代码在 `mimo_tts.py` 中读取 `MIMO_API_KEY`；若 Codex 尚未刷新进程环境，也会读取当前 Windows 用户变量。生成的 WAV 会放进 AE 工程。

密钥仅供 API 调用，不写入导演稿、AE 工程和来源清单。2026-09-29 已用 [MiMo 版八王之乱导演稿](<examples/eight-princes-291-306-story-v2.mimo.director.json>)生成六段 WAV、84 秒总旁白和可编辑 AEP；产物位于 `output/eight-princes-story-v2-mimo/`。

`mimo-v2.5-tts-voiceclone` 需要上传参考音频；真人声音只应在获授权的范围内使用。此前 v2 案例采用原创音色设计；上面的 v4 案例基于用户声明已获授权的参考音频。
