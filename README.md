# AIRapStudio (Autonomous AI Rap Video Generation Engine)

`airap` 是一个工业级全自动 AI 说唱音乐视频（AI Rap Video）生成引擎，深度融合音乐韵律计算、音频下拍分析、高帧率口型视素映射、节拍卡点剪辑与动力学动态字幕。

## 架构体系

- **`airap.lyrics`**: Flow 与多押分析器、16-Bar 节拍对齐调度器。
- **`airap.audio`**: 毫秒级 BPM 测算、瞬态能量（Transient）检测、音素时间戳强制对齐。
- **`airap.avatar`**: 极速说唱音素-视素（Phoneme-to-Viseme）对齐、防抖口型合成适配器与律动点头模拟。
- **`airap.director`**: 节拍剪辑导演、多轨道时间线调度器、镜头缩放/抖动/故障动效。
- **`airap.subtitles`**: 动力学卡点字幕生成器、逐词高亮（Karaoke Bar Highlight）、ASS/SRT 导出。
- **`airap.compositor`**: FFmpeg 多轨道视频终审合成器。
- **`airap.pipeline`**: 端到端全自主生成总控流水线。

## 快速使用

```bash
# 运行完整端到端测试
pytest -v

# 命令行一键生成说唱 MV
python3 -m airap.cli generate --lyrics "sample.txt" --bpm 130 --output "output.mp4"
```
