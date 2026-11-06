# Qwen Voice Studio 3.6

[English](README.en.md) | [架构](docs/ARCHITECTURE.md) | [复审报告](docs/REVIEW.md) | [来源与许可](THIRD_PARTY_NOTICES.md)

一个可以**独立安装和运行**的本地 Qwen3-TTS 创作应用。内置 WebUI、模型发现、单任务队列、音频库，以及 CPU、GPU、GPU + CPU 混合卸载策略。使用 FastAPI 和原生 HTML/CSS/JavaScript；**无需另外克隆、安装或指定任何第三方 WebUI**，也无需 Node.js 或 ComfyUI。

> `qwen-tts`、PyTorch、Transformers、Accelerate 等仍是正常的 Python 依赖，安装器负责准备；模型权重需由用户合法获取。项目不包含模型文件或 CUDA/驱动。

## Windows + uv：安装与启动

在解压后的项目目录运行 PowerShell：

```powershell
.\install.ps1
.\start.ps1
```

默认在项目 `.venv` 中安装 Python 3.12；如果已有经过验证的环境，明确传入它以复用当前 Torch/CUDA 构建：

```powershell
.\install.ps1 -PythonPath "..\.venv\Scripts\python.exe"
.\start.ps1
```

打开 `http://127.0.0.1:7861`。如果 PowerShell 限制脚本执行，可在**当前会话**临时运行 `Set-ExecutionPolicy -Scope Process Bypass`。

安装脚本会保留已经安装的 Torch/TorchAudio/TorchVision 版本，包括 CUDA 构建后缀；新环境会请求 uv 自动选取可用的 PyTorch 后端。安装完成执行 `uv pip check`；不会替用户更新显卡驱动或自动下载语音权重。可用以下命令查看依赖：

```powershell
uv pip list --python .\.venv\Scripts\python.exe
```

推理设备与预算由用户自主选择。应用不会按显卡型号、显存空闲量或模型估算大小拒绝 GPU 加载，也不会悄悄把 GPU 任务改为 CPU；如果实际加载失败，会给出分类错误。混合模式取决于安装的推理依赖与模型兼容性，不能保证在所有硬件上成功。

## 自动识别本地模型

在「设置 → 模型」可以点击「选择文件夹」打开 **Windows 原生目录选择器**，选定包含 `config.json` 的模型目录后再点「添加」。在折叠的「扫描选项」里，可反复点击「添加文件夹」逐个加入扫描目录；支持删除、去重和手动编辑多行路径。「保存并扫描」会先保存本次目录变更再执行扫描。

**注意**：弹窗由运行 Studio 的 **Windows 本机**打开，并选择该机器上的文件夹，不是远程浏览器所处设备。非 Windows、后台服务或无交互桌面的环境会继续提供手动输入。原生选择需要系统自带 Windows PowerShell 和可交互的 Windows 桌面；它不会把模型权重复制到应用内。默认扫描项目 `models`、父目录 `models` 和本地 Hugging Face 缓存，也可在启动时指定：

```powershell
.\start.ps1 -ModelsRoot "D:\Models\TTS"
.\start.ps1 -ModelPath "D:\Models\Qwen3-TTS-12Hz-1.7B-VoiceDesign"
```

支持的**完整**模型（依据 `config.json` 与权重 / tokenizer 文件判断，不只按名称识别）：

| 模型 | 主要能力 |
|---|---|
| VoiceDesign 1.7B | 根据文字说明设计声音 |
| Base 0.6B / 1.7B | 授权参考音频克隆与文生语音 |
| CustomVoice 0.6B / 1.7B | 预设说话人（指令控制以模型能力为准） |

**参考声音克隆必须选择 Base 模型**。普通克隆需要上传音频及准确参考文本；勾选「仅使用声纹」时可省略转录。其他两个模型不能将参考音频作为克隆条件。

不支持 GGUF、LoRA、单独 tokenizer、不完整分片或未知音频架构直接混入官方推理流程。扫描默认有限深度和目录数量，不遍历整盘、不自动从网络下载模型。

## 内置推理设备与故障定位

- **自动**：存在 CUDA 时按设备是否支持 BF16 选择 BF16 或 FP32；无 CUDA 时使用 CPU。**不探测空闲显存来决策，不预测权重大小，不自动更改预算**。
- **GPU**：支持 FP32、BF16（硬件允许时），及显式实验性 FP16。
- **GPU + CPU**：FP32，通过 Accelerate 的分层卸载，由 `studio/inference_runtime.py` 内置设备修正实现；独立设置 GPU/CPU 权重预算。程序将预算原样交给依赖库，而非按硬件剩余资源自动缩减。
- **CPU**：FP32，用于稳定性对照。

混合卸载对执行设备、解码层不可拆分与语音 tokenizer 放置所做的修改，直接随本项目源码发布，不会寻找外部 Git 仓库。技术依据及 GPL-3.0 归属详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。所有选项运行时都复用 `qwen-tts` 官方 Python API。

任务失败会标明**模型加载 / 参考音频编码 / 语音生成 / 波形校验**等阶段、允许公开的错误类型和诊断代号；不会直接把私人台词、参考音频或本机路径写入错误消息。`code_predictor_config is None`、`encoder_config is None` 等模型默认初始化信息本身不是失败原因。

```powershell
.\start.ps1 -DataDir "D:\VoiceStudioData"
```

首次指定的 `-DataDir` 应指向您之前已备份/使用的数据目录；否则新解压的版本使用自身 `.local`，旧数据不会自动搬迁。首次加载如仍看到旧界面，可按 `Ctrl+Shift+R` 强制刷新浏览器。

## UI、输出和隐私

中文/英文界面、无衬线/衬线排版、深浅色主题、文字比例、紧凑/舒适布局、可调双栏与移动端纵向布局。支持生成、批量短句、上传及录音、波形试听、历史记录、音色预设、WAV/FLAC 导出；安装 FFmpeg 后可导出 MP3。所有界面资源均本地提供，不访问外部字体/CDN。

- 仅监听 `127.0.0.1`，默认单用户；**不可直接暴露公网**。
- 模型与参考音频、历史记录存于本机。创作历史**未加密**，需要注意文件权限和备份。
- 草稿长期持久化默认关闭，但台词等草稿会在当前标签页会话中暂存用于刷新恢复；可清空项目创建的音频、任务和预设，不删除模型权重。
- 仅使用已获得授权的参考声音。
- `-DataDir` 可指定数据目录；不要在两个应用实例中同时使用同一 SQLite 数据库。

## 测试、交付与边界

项目包含 Python 单测、Node.js（仅开发用）前端检查及 Chromium 浏览器回归脚本。`docs/REVIEW.md` 记录此前复核；`docs/FINAL_VERIFICATION_V350.md` 记录此前 UI 与状态恢复复核，`docs/FINAL_VERIFICATION_V360.md` 记录本次原生选择/路径管理复核；`docs/TARGET_ACCEPTANCE.md` 记录真实 Windows 设备验收步骤。

```powershell
# 开发者回归（可选）
python -m pytest -q
node --test tests/ui_i18n.test.mjs
python tools/release_check.py
```

项目源码使用 GPL-3.0；模型权重与一般依赖保留各自许可。压缩包不含个人目录、Token、私人音频或模型权重。
