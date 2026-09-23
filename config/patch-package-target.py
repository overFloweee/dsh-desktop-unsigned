#!/usr/bin/env python3
"""CI 专用补丁：让官方的桌面打包链能在**未签名**模式下跑通 macOS 构建。

只作用于 CI 检出的上游副本（src/），不改上游仓库。共三处，全部幂等：

1. apps/desktop/scripts/package-target.ts
   darwin 上**无论是否 prepare-only** 都会 `withMacOSSigningKeychain(...)`（导入 p12 到临时
   keychain，自签名 p12 会被 `security import` 拒绝）→ 改成直接调用 packageTarget。
   该 import 随之变成未使用变量，tsc 的 noUnusedLocals 会报 TS6133（实测踩过）→ 一并注释。

2. apps/desktop/scripts/prepare-dsh.ts
   darwin 上会 `signMacOSRuntime(...)` 签名 dsh 输出树与 primary-runtime，走 macOS 签名
   缓存策略（内部调 `/usr/bin/codesign` 校验 probe）→ 未签名构建直接跳过该分支；
   同样处理随之失效的两个 import（TS6133）。

用法（在 src/ 目录下）：python3 <this-file>
"""
from pathlib import Path
import sys

PACKAGE_TARGET = Path("apps/desktop/scripts/package-target.ts")
PREPARE_DSH = Path("apps/desktop/scripts/prepare-dsh.ts")

# —— 补丁 1：package-target.ts ——
PT_IMPORT_OLD = "import { withMacOSSigningKeychain } from './macos-signing-keychain.mjs'"
PT_IMPORT_NEW = "// [CI unsigned patch] withMacOSSigningKeychain 不再使用（见下方 macOS 打包分支）"
PT_CALL_OLD = "\n".join([
    "      await packagingStep(run.directory, 'macos-package', () => withMacOSSigningKeychain(environment,",
    "        signingEnvironment => packageTarget(invocation, signingEnvironment, run)), secrets)",
])
PT_CALL_NEW = "\n".join([
    "      // [CI unsigned patch] 跳过 keychain 导入：本流程不签名、不公证",
    "      await packagingStep(run.directory, 'macos-package', () => packageTarget(invocation, environment, run), secrets)",
])

# —— 补丁 2：prepare-dsh.ts ——
PD_BLOCK_OLD = "\n".join([
    "    if (process.platform === 'darwin') {",
    "      await packagingStep(process.env.DSH_DESKTOP_PACKAGING_RUN_DIR, 'sign:dsh-native', () => signMacOSRuntime(DSH_OUTPUT_ROOT, resolveDesktopAppId(process.env), resolveMacOSSigningEnvironment(process.env), join(BUILD_PATHS.root, 'signature-cache')))",
    "      await packagingStep(process.env.DSH_DESKTOP_PACKAGING_RUN_DIR, 'sign:primary-native', () => signMacOSRuntime(join(RUNTIME_ROOT, 'primary-runtime'), resolveDesktopAppId(process.env), resolveMacOSSigningEnvironment(process.env), join(BUILD_PATHS.root, 'signature-cache')))",
    "    }",
])
PD_BLOCK_NEW = "\n".join([
    "    // [CI unsigned patch] 跳过 dsh 输出树与 primary-runtime 的 Mach-O 签名（未签名构建）",
])
PD_IMPORTS = [
    ("  resolveMacOSSigningEnvironment,", "  // [CI unsigned patch] resolveMacOSSigningEnvironment,"),
    ("  signMacOSRuntime,", "  // [CI unsigned patch] signMacOSRuntime,"),
]


def patch(path: Path, replacements, label: str) -> list[str]:
    """Apply (old, new) replacements; skip ones already applied; error if an anchor is missing."""
    if not path.is_file():
        print(f"patch: 找不到 {path}（cwd={Path.cwd()}）", file=sys.stderr)
        raise SystemExit(1)
    source = path.read_text(encoding="utf8")
    applied = []
    for old, new in replacements:
        if new in source:
            continue
        if old not in source:
            print(f"patch: [{label}] 锚点没找到，需要更新补丁: {old.strip()[:70]}", file=sys.stderr)
            raise SystemExit(1)
        source = source.replace(old, new, 1)
        applied.append(label)
    if applied:
        path.write_text(source, encoding="utf8")
    return applied


def main() -> int:
    applied = []
    applied += patch(PACKAGE_TARGET, [(PT_IMPORT_OLD, PT_IMPORT_NEW), (PT_CALL_OLD, PT_CALL_NEW)], "package-target")
    applied += patch(PREPARE_DSH, [(PD_BLOCK_OLD, PD_BLOCK_NEW), *PD_IMPORTS], "prepare-dsh")
    print(f"patch: {'已应用 ' + '/'.join(applied) if applied else '已打过，跳过'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
