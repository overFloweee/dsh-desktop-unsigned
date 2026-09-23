#!/usr/bin/env python3
"""CI 专用补丁：跳过 macOS 签名 keychain 导入。

背景：官方 `package-target.ts` 在 darwin 上**无论是否 prepare-only** 都会调用
`withMacOSSigningKeychain(...)`（把 CSC_LINK 指向的 p12 导入临时 keychain）。未签名自建
构建不需要它，而且自签名 p12 会被 `security import` 拒绝。

这里把那一处调用改成直接调用 `packageTarget(invocation, environment, run)`，不再套 keychain。
只作用于 CI 检出的上游副本，不改上游仓库。

用法（在 src/ 目录下）：python3 <this-file>
"""
from pathlib import Path
import sys

TARGET = Path("apps/desktop/scripts/package-target.ts")

OLD = "\n".join([
    "      await packagingStep(run.directory, 'macos-package', () => withMacOSSigningKeychain(environment,",
    "        signingEnvironment => packageTarget(invocation, signingEnvironment, run)), secrets)",
])

NEW = "\n".join([
    "      // [CI unsigned patch] 跳过 keychain 导入：本流程不签名、不公证",
    "      await packagingStep(run.directory, 'macos-package', () => packageTarget(invocation, environment, run), secrets)",
])


def main() -> int:
    if not TARGET.is_file():
        print(f"patch: 找不到 {TARGET}（cwd={Path.cwd()}）", file=sys.stderr)
        return 1
    source = TARGET.read_text(encoding="utf8")
    if NEW in source:
        print("patch: 已打过，跳过")
        return 0
    if OLD not in source:
        print("patch: 锚点没找到——上游改了这段代码，需要更新补丁", file=sys.stderr)
        return 1
    TARGET.write_text(source.replace(OLD, NEW, 1), encoding="utf8")
    print("patch: 已跳过 withMacOSSigningKeychain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
