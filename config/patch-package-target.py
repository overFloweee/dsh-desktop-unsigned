#!/usr/bin/env python3
"""CI 专用补丁：跳过 macOS 签名 keychain 导入。

背景：官方 `package-target.ts` 在 darwin 上**无论是否 prepare-only** 都会调用
`withMacOSSigningKeychain(...)`（把 CSC_LINK 指向的 p12 导入临时 keychain）。未签名自建
构建不需要它，而且自签名 p12 会被 `security import` 拒绝。

改动两处（只作用于 CI 检出的上游副本）：
  1. 调用点：`withMacOSSigningKeychain(environment, cb => packageTarget(...))`
     → 直接 `packageTarget(invocation, environment, run)`
  2. 该模块的 import 行：删掉后它会变成未使用变量，tsc 的 noUnusedLocals 会报
     `error TS6133: 'withMacOSSigningKeychain' is declared but its value is never read`
     （实测踩过），所以一并注释掉。

用法（在 src/ 目录下）：python3 <this-file>
"""
from pathlib import Path
import sys

TARGET = Path("apps/desktop/scripts/package-target.ts")

CALL_OLD = "\n".join([
    "      await packagingStep(run.directory, 'macos-package', () => withMacOSSigningKeychain(environment,",
    "        signingEnvironment => packageTarget(invocation, signingEnvironment, run)), secrets)",
])
CALL_NEW = "\n".join([
    "      // [CI unsigned patch] 跳过 keychain 导入：本流程不签名、不公证",
    "      await packagingStep(run.directory, 'macos-package', () => packageTarget(invocation, environment, run), secrets)",
])

IMPORT_OLD = "import { withMacOSSigningKeychain } from './macos-signing-keychain.mjs'"
IMPORT_NEW = "// [CI unsigned patch] withMacOSSigningKeychain 不再使用（见下方 macOS 打包分支）"


def main() -> int:
    if not TARGET.is_file():
        print(f"patch: 找不到 {TARGET}（cwd={Path.cwd()}）", file=sys.stderr)
        return 1
    source = TARGET.read_text(encoding="utf8")
    changed = []

    if IMPORT_NEW in source:
        pass
    elif IMPORT_OLD in source:
        source = source.replace(IMPORT_OLD, IMPORT_NEW, 1)
        changed.append("import")
    else:
        print("patch: import 锚点没找到——上游改了这段代码，需要更新补丁", file=sys.stderr)
        return 1

    if CALL_NEW in source:
        pass
    elif CALL_OLD in source:
        source = source.replace(CALL_OLD, CALL_NEW, 1)
        changed.append("call")
    else:
        print("patch: 调用点锚点没找到——上游改了这段代码，需要更新补丁", file=sys.stderr)
        return 1

    if changed:
        TARGET.write_text(source, encoding="utf8")
        print(f"patch: 已应用（{'/'.join(changed)}）")
    else:
        print("patch: 已打过，跳过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
