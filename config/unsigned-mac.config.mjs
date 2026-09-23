// 未签名 macOS 构建用的 electron-builder 配置。
//
// 思路：**复用官方工厂**（createElectronBuilderConfig），这样"准备树 → app.asar /
// asarUnpack / extraResources / 版本与元数据"全部与官方打包一致；然后只改三件事：
//
//   1) 关掉签名与公证：mac.identity = null, notarize = false, hardenedRuntime = false,
//      forceCodeSigning = false（官方 mac 段是 forceCodeSigning: true + notarize: true）
//   2) 去掉依赖真实签名/公证/上传环境的钩子：afterSign（验签）、afterPack（写 app-update.yml +
//      运行时校验）、beforePack（Windows 资源准备 + policy 校验）、artifactBuildCompleted（dmg 公证）
//   3) 目标只出 dir（.app），不出 dmg/zip
//
// ⚠️ 官方工厂在 darwin 上会校验签名/公证环境变量的**形状**（非空、teamId 10 位大写字母数字、
// identity 不带 "Developer ID Application:" 前缀），所以 CI 必须给一套格式合法的假值——它们
// 只会被用来通过校验，不会被用来真签名（identity 已被下面覆盖成 null）。
import { createElectronBuilderConfig } from './scripts/electron-builder-config.mjs'

const config = createElectronBuilderConfig(process.env)

config.mac = {
  ...config.mac,
  identity: null,
  notarize: false,
  hardenedRuntime: false,
  forceCodeSigning: false,
  target: ['dir'],
}

delete config.afterSign
delete config.afterPack
delete config.beforePack
delete config.artifactBuildCompleted

config.directories = { ...config.directories, output: 'dist-unsigned' }

export default config
