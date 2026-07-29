# 圆头耄耋桌宠

一只透明、置顶、会随机发呆/走路/睡觉，也能吃文件和实时聊天的圆头橘猫桌宠。
工程使用 Tauri 2、React、TypeScript 和 Rust，目标平台为 Windows 10/11 与 macOS 13+。

## 已实现

- 六套真实包浆风格动画，每套严格 16 张 512×512 透明 PNG；
- 可测试的集中状态机、随机行为、左右游走与边界反向；
- 6 logical px / 500 ms 点击拖动判定，抚摸与可调哈气概率；
- 原生文件拖放、路径去重与 Rust 安全校验，仅调用系统回收站/废纸篓；
- 独立无标题栏聊天窗，OpenAI-compatible SSE 流、停止、Markdown 和本地历史；
- API Key 只保存到系统凭据存储，不进入前端 Store；
- 设置持久化、桌宠位置恢复/可见区域校正、托盘/菜单栏入口；
- Windows/macOS 打包配置、单元测试和 GitHub Actions。

## 本地运行

前置条件：Node.js 20+、pnpm 10、稳定版 Rust，以及
[Tauri 2 平台依赖](https://v2.tauri.app/start/prerequisites/)。

```bash
pnpm install
pnpm tauri dev
```

浏览器 UI 预览（系统窗口、回收站和凭据功能不可用）：

```bash
pnpm dev
```

## 测试与构建

```bash
pnpm test
pnpm lint
pnpm build
cd src-tauri && cargo fmt --check && cargo clippy -- -D warnings && cargo test
cd ..
pnpm tauri build
```

Windows 默认构建 NSIS/MSI；macOS 默认构建 `.app`/`.dmg`。无签名证书时可生成开发测试
产物；公开发布 macOS 包仍需要 Apple Developer 签名与 notarization。

## 模型配置

右键桌宠打开对话，点击齿轮进入设置：

1. 填写 HTTPS Base URL（例如服务的 `/v1` 根路径）；
2. 填写模型名；
3. 输入 API Key 并保存；
4. 点击“测试连接”。

请求由 Rust 后端发出，默认调用 `<baseUrl>/chat/completions`，连接测试调用
`<baseUrl>/models`。Key 以 `maodie-desktop-pet / openai-compatible` 标识写入 Windows
Credential Manager 或 macOS Keychain。聊天历史最多保留 50 条，可关闭和清空。

## 文件投喂安全

投喂只接受本地普通文件。文件夹、符号链接、相对路径、系统保护目录和应用自身目录会被
拒绝；实现中没有 `remove_file`、`remove_dir_all` 或 shell 删除命令。成功文件进入操作系统
回收站/废纸篓，可由用户恢复。文件名、路径和内容不会被发送给模型。

首次测试请使用临时创建、可丢弃的文件，并确认它出现在回收站后再投喂重要文件。

## 替换动画素材

业务代码只依赖固定接口：

```text
src/assets/pet/<sitting|walking|sleeping|happy|petting|hissing>/00.png ... 15.png
```

替换时保持 RGBA PNG、512×512、统一承重点和文件名即可，无需改代码。`walking` 只需朝右，
向左由程序镜像。当前统一身份锚点、关键帧源表、过渡帧和质量报告位于
`artifacts/asset-work/v2/`。素材处理脚本会保持原比例、统一承重点与毛色，并把关键帧和
真正的 50% 过渡帧交错输出：

```bash
PYTHONPATH=/path/to/opencv-python-headless \
  python3 scripts/process_animation_assets.py
```

参考盘点与生成记录见 [关键帧盘点](docs/keyframe-inventory.md) 和
[素材生成报告](docs/asset-generation-report.md)。

## 隐私

- 不含遥测；
- 不读取或上传投喂文件内容；
- 不记录完整文件路径、聊天正文、请求头或 API Key；
- 设置和聊天历史仅保存在本机；
- 角色系统提示见 `src/skills/maodie.system.md`。

## 已知限制

- 已在当前环境通过 TypeScript 类型检查、ESLint、Vitest 和 Vite 生产构建。
  Rust 源码已通过 `cargo fmt --check`；Linux 验证容器缺少 C linker 与 GTK/WebKit 系统库，
  因而后端完整编译留给配置齐全的 Windows/macOS CI。
- 文件投喂只支持普通本地文件，不支持文件夹、网络共享、云占位文件和符号链接。
- 动画由 8 个动作关键帧与 8 个相邻过渡帧组成；walking/petting 默认 10 FPS，避免快速抽动。
- 应用未附带签名证书、自动更新服务或发布凭据。

状态图见 [架构说明](docs/architecture.md)，实机测试请使用
[手工验收模板](docs/manual-acceptance-template.md)。

## 素材版权

代码采用 MIT License。用户提供的角色参考图片及由其衍生的动画不因代码许可证而自动获得
再分发授权；使用者需自行确认原始素材权利。
