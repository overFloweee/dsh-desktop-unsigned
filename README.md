# dsh-desktop-build（自建未签名 macOS 桌面包）

用 **GitHub Actions** 把**官方** [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)
的桌面端（`apps/desktop`）打成 **macOS arm64 未签名 `.app`**，供本地自用。

> ⚠️ **这不是官方发布**。官方 macOS 打包链要求 Developer ID 证书 + 公证（`apps/desktop/README.md`），
> 本流程刻意绕过签名/公证，产物在新机器上会被 Gatekeeper 拦，需要右键 → 打开（或清 quarantine）。

## 为什么这么做

官方桌面端**没有任何公开分发的成品包**（GitHub Releases 全部 `assets=0`、无 `desktop-v*` tag、
`dsh-desk/...` feed 404、官网/文档无下载入口）。而官方打包入口在 macOS 上是硬性的
"必须签名 + 公证"：

- `apps/desktop/scripts/package-target.ts`：`--unsigned` 只允许 `win-x64`
- `apps/desktop/scripts/electron-builder-config.mjs`：`unsigned && platform !== 'win32'` 直接抛错；
  `mac.notarize: true` + `afterSign` 验签钩子 + `forceCodeSigning: true`

所以这里拆成两步：

1. **官方 `pnpm run prepare:desktop`**（= `package-target --prepare-only`）——准备运行时与 dsh 投影树，
   **不触发任何签名/公证前置**，因此不需要 Apple 凭据；
2. **自己的 electron-builder 配置** [config/unsigned-mac.config.mjs](config/unsigned-mac.config.mjs)
   ——复用官方工厂（保留 `files` / `asarUnpack` / `extraResources` 的资源接线），只覆盖：
   `identity: null`、`notarize: false`、`hardenedRuntime: false`、`forceCodeSigning: false`、
   `target: ['dir']`，并删掉 `afterSign` / `afterPack` / `beforePack` / `artifactBuildCompleted` 这些
   依赖真实签名/公证环境的钩子。

## 用法

1. 打开 **Actions → package-macos-unsigned → Run workflow**
   - `tag`：上游 tag，例如 `dsh-v0.1.7-alpha.1`（默认值）
   - `publish_release`：勾上会建一个 Release，直接给下载链接
2. 跑完（约 20–40 分钟，取决于依赖与运行时下载）在 **Release** 或 **Artifacts** 下载
   `DeepSeek-Harness-<tag>-mac-arm64-unsigned.zip`
3. 本地解压安装：

```bash
unzip DeepSeek-Harness-*-mac-arm64-unsigned.zip -d /tmp/dsh
cp -R "/tmp/dsh/DeepSeek Harness.app" /Applications/
xattr -dr com.apple.quarantine "/Applications/DeepSeek Harness.app"   # 或右键 → 打开
```

## 已知限制

- **未签名、未公证**：Gatekeeper 会拦；企业 MDM/严格策略可能直接拒开。
- **没有自动更新**：`app-update.yml` 依赖签名，这里不写；升级就重跑一遍流水线。
- **账号登录相关能力可能不完整**：官方 README 的 *Known limitations* 写着 "Account sign-in is not connected"。
- **与官方桌面壳同版本耦合**：桌面壳与 `@deepseek-ai/dsh` 必须同版本（官方设计），本流程打出来的
  就是该 tag 自带的 dsh 版本；它和 CLI 的版本一致性需要你自己注意。
- 首次运行可能需要多次迭代（上游打包脚本会变），失败就贴日志。
