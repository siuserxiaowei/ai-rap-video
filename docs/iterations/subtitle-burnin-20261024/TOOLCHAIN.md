# 本地 ASS 字幕工具链与复现

当前工作区已在 `.workbench/toolchains/ass-ffmpeg-8.1.1/bin/` 构建 FFmpeg/FFprobe8.1.1，包含 libass0.17.5。这套工具关闭网络协议，仅供本地合成；原 `/opt/homebrew/bin/ffmpeg` 解析路径与文件哈希保持不变。二进制、字体和生成媒体未提交到Git。应用不会自行下载安装工具。

## 运行已构建的工具

在项目根目录使用现有 `.venv/bin/python`：

```bash
.venv/bin/python -m airap.cli preview \
  --lyrics "中文烧录预览" --bpm 240 \
  --ffmpeg .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg \
  --ffprobe .workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe \
  --subtitle-mode required --subtitle-font "Arial Unicode MS" \
  --output subtitle-preview.mp4 --output-dir output --json
```

`required` 要求所选FFmpeg支持ASS且实际烧录；`off` 不烧录；`auto` 根据所选构建能力决定。默认仍发现PATH工具，因此本机默认FFmpeg在auto模式仍可能返回 `subtitles_burned=false`。显式无效工具不会退回其他版本。`--subtitle-font` 是请求的字体族，不构成实际字体匹配证明；其他机器应选择其已安装字体。

真实ASS测试需要显式测试环境变量。以下命令执行全部529项，包括7项真实特殊路径字幕用例；不配置这两个变量时，仅这7项可选用例会跳过：

```bash
AIRAP_TEST_FFMPEG="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffmpeg" \
AIRAP_TEST_FFPROBE="$PWD/.workbench/toolchains/ass-ffmpeg-8.1.1/bin/ffprobe" \
.venv/bin/python -m pytest -q
```

## 重建（macOS arm64）

构建助手使用Python3.12+；当前 `.venv` 为3.15。应用本身的Python3.10+最低版本不变。需要macOS命令行编译工具，以及现有Homebrew freetype、fribidi、harfbuzz、fontconfig和x264库。此次只新增pkgconf3.0.10与libunibreak8.0，未升级既有依赖。完整ffmpeg-full包的安装预检另存于研究记录；本次没有安装该包。

上游源码先核对SHA-256，再解压构建。两个归档的URL及校验值固定在 `scripts/build_subtitle_toolchain.py` 的SOURCES中；下载中断或内容不符时助手会拒绝继续：

```bash
mkdir -p /tmp/airap-subtitle-sources
curl -fL --retry 3 https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz \
  -o /tmp/airap-subtitle-sources/ffmpeg-8.1.1.tar.xz
gh release download 0.17.5 --repo libass/libass \
  --pattern libass-0.17.5.tar.xz --dir /tmp/airap-subtitle-sources
.venv/bin/python scripts/build_subtitle_toolchain.py \
  --source-dir /tmp/airap-subtitle-sources \
  --artifact-dir artifacts/tmp/toolchain-rebuild --jobs 4
```

助手只进行本地构建与安装到项目工具目录，不下载源码、不切换全局FFmpeg。实际编译参数、步骤退出码、上游哈希与二进制哈希见 `artifacts/iterations/subtitle-burnin-20261024/toolchain-build.json`；官方开发资料见 `research/toolchains/ass-ffmpeg/20261024/manifest.json`。这份配方验证功能可复现，不承诺不同系统库版本的二进制逐字节相同。

## 实际验收边界

`scripts/verify_subtitle_burnin.py` 比较同源黑色视频的字幕开/关样本。0.1秒和0.9秒差异为0，0.5秒字幕期差异为2996像素，并保存实际解码帧。主线程查看了受控、竖屏、横屏三个样本中的“中文烧录预览”，未见这些字形缺失或被裁切。四次真实全高清CLI覆盖required、auto与off，全部完成音视频流探测和完整解码；无ASS工具的required预检拒绝且保留旧输出。

这是本地字幕与所选样本验收，不是浏览器UI、AI人声、人物动画、快Rap口型或供应商计费验收。合成测试帧与视频保留于忽略的 `artifacts/tmp/subtitle-burnin-20261024/` 供本机复核，不含真人素材。
