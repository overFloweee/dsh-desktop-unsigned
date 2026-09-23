#!/usr/bin/env python3
"""CI 专用补丁：让官方桌面打包链能在**未签名**模式下跑通 macOS 构建。

只作用于 CI 检出的上游副本（src/），不改上游仓库。两步，均幂等：

第一步 · 定点补丁
  1. apps/desktop/scripts/package-target.ts
     darwin 上**无论是否 prepare-only** 都调用 `withMacOSSigningKeychain(...)`（把 CSC_LINK 的
     p12 导入临时 keychain；自签名 p12 会被 `security import` 拒绝）→ 改成直接调 packageTarget。
  2. apps/desktop/scripts/prepare-dsh.ts
     darwin 上会 `signMacOSRuntime(...)` 签名 dsh 输出树与 primary-runtime（内部走 macOS 签名
     缓存策略 → `/usr/bin/codesign` 校验 probe）→ 跳过该分支。

第二步 · 自动清理失效 import
  被跳过的那几行往往是某些 import 的**唯一**使用点，删掉后 tsc 的 noUnusedLocals 会逐个报
  TS6133（实测连续踩了 `withMacOSSigningKeychain`、`signMacOSRuntime`、
  `resolveMacOSSigningEnvironment`、`resolveDesktopAppId`）。这里统一检测：多行 import 列表里
  某个标识符在文件正文里已无引用，就把那一行注释掉，避免逐个打补丁。

用法（在 src/ 目录下）：python3 <this-file>
"""
from pathlib import Path
import re
import sys

PACKAGE_TARGET = Path("apps/desktop/scripts/package-target.ts")
PREPARE_DSH = Path("apps/desktop/scripts/prepare-dsh.ts")

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

PD_BLOCK_OLD = "\n".join([
    "    if (process.platform === 'darwin') {",
    "      await packagingStep(process.env.DSH_DESKTOP_PACKAGING_RUN_DIR, 'sign:dsh-native', () => signMacOSRuntime(DSH_OUTPUT_ROOT, resolveDesktopAppId(process.env), resolveMacOSSigningEnvironment(process.env), join(BUILD_PATHS.root, 'signature-cache')))",
    "      await packagingStep(process.env.DSH_DESKTOP_PACKAGING_RUN_DIR, 'sign:primary-native', () => signMacOSRuntime(join(RUNTIME_ROOT, 'primary-runtime'), resolveDesktopAppId(process.env), resolveMacOSSigningEnvironment(process.env), join(BUILD_PATHS.root, 'signature-cache')))",
    "    }",
])
PD_BLOCK_NEW = "    // [CI unsigned patch] 跳过 dsh 输出树与 primary-runtime 的 Mach-O 签名（未签名构建）"

MARK = "// [CI unsigned patch]"


def apply_replacements(path: Path, replacements, label: str) -> list[str]:
    if not path.is_file():
        print(f"patch: 找不到 {path}（cwd={Path.cwd()}）", file=sys.stderr)
        raise SystemExit(1)
    source = path.read_text(encoding="utf8")
    applied = []
    for old, new in replacements:
        if new in source:
            continue
        if old not in source:
            print(f"patch: [{label}] 锚点没找到，需要更新补丁：{old.strip().splitlines()[0][:80]}", file=sys.stderr)
            raise SystemExit(1)
        source = source.replace(old, new, 1)
        applied.append(label)
    if applied:
        path.write_text(source, encoding="utf8")
    return applied


def import_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """返回多行 import 语句的行号区间（含首尾）。"""
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if re.match(r"\s*import\b", lines[i]) and "from" not in lines[i]:
            start = i
            while i < len(lines) and not re.search(r"from\s+['\"]", lines[i]):
                i += 1
                if i >= len(lines):
                    break
            spans.append((start, min(i, len(lines) - 1)))
        i += 1
    return spans


def neutralize_unused_imports(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf8").split("\n")
    spans = import_blocks(lines)
    if not spans:
        return []
    masked = set()
    for start, end in spans:
        masked.update(range(start, end + 1))
    body = "\n".join(line for idx, line in enumerate(lines) if idx not in masked)
    commented: list[str] = []
    for start, end in spans:
        for idx in range(start, end + 1):
            match = re.match(r"^(\s*)([A-Za-z_$][\w$]*)(,?)\s*$", lines[idx])
            if not match:
                continue
            indent, name, comma = match.groups()
            if name in {"import", "type", "from"} or MARK in lines[idx]:
                continue
            if re.search(r"\b" + re.escape(name) + r"\b", body):
                continue
            lines[idx] = f"{indent}{MARK} {name}{comma}"
            commented.append(name)
    if commented:
        path.write_text("\n".join(lines), encoding="utf8")
    return commented


def main() -> int:
    applied = []
    applied += apply_replacements(PACKAGE_TARGET, [(PT_IMPORT_OLD, PT_IMPORT_NEW), (PT_CALL_OLD, PT_CALL_NEW)], "package-target")
    applied += apply_replacements(PREPARE_DSH, [(PD_BLOCK_OLD, PD_BLOCK_NEW)], "prepare-dsh")
    cleaned: list[str] = []
    for path in (PACKAGE_TARGET, PREPARE_DSH):
        cleaned += neutralize_unused_imports(path)
    summary = []
    if applied:
        summary.append("定点补丁 " + "/".join(applied))
    if cleaned:
        summary.append("顺手清理失效 import: " + ", ".join(cleaned))
    print("patch: " + ("；".join(summary) if summary else "已打过，无需改动"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
