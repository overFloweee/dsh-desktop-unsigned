#!/usr/bin/env python3
"""校验打出来的 .app 里，shell（Electron 主进程）的运行时依赖**闭包**是否完整。

背景：上游把 shell 运行时需要的包声明成 devDependencies（甚至完全不声明），而
electron-builder 只收集 **dependencies**、并且**不跟随 workspace 链接包的依赖** ——
于是产物一层层缺包，表现为启动时连续弹
`Error [ERR_MODULE_NOT_FOUND]: Cannot find package '@deepseek-ai/…'`。

CI 里已用 `config/patch-package-target.py` 把整条闭包提升进 dependencies；这里校验
**结果**：把产物里已打包的 `@deepseek-ai/*` 逐个扫它们的裸 import，凡是 import 到
但产物里没有的，就在仓库检出里继续往下追，最后一次性报出**完整缺失清单**。

用法：python3 config/verify-app-deps.py "<App.app>" [repo-root]
"""
from __future__ import annotations

import glob
import json
import os
import re
import struct
import sys

SPEC = re.compile(r"""(?:from|require\()\s*['"](@deepseek-ai/[^'"]+)['"]""")


def load_asar(asar: str) -> tuple[dict[str, tuple[int, int]], object]:
    """返回 {asar 内路径: (offset, size)} 与可用于 seek 的文件句柄。"""
    handle = open(asar, "rb")
    head = handle.read(16)
    payload = struct.unpack("<I", head[4:8])[0]
    json_length = struct.unpack("<I", head[12:16])[0]
    header = json.loads(handle.read(json_length).decode("utf8"))
    base = 8 + payload

    entries: dict[str, tuple[int, int]] = {}

    def walk(node: dict, prefix: str = "") -> None:
        for name, child in (node.get("files") or {}).items():
            path = prefix + name
            if "files" in child:
                walk(child, path + "/")
            elif "offset" in child:
                entries[path] = (base + int(child["offset"]), int(child["size"]))

    walk(header)
    return entries, handle


def workspace_dirs(repo: str) -> dict[str, str]:
    """仓库里 workspace 包名 → 目录（用于递归追踪未打包的包）。"""
    found: dict[str, str] = {}
    patterns = ["packages/**/package.json", "vendor/**/package.json", "apps/*/package.json"]
    for pattern in patterns:
        for path in glob.glob(os.path.join(repo, pattern), recursive=True):
            try:
                manifest = json.load(open(path, encoding="utf8"))
            except Exception:
                continue
            name = manifest.get("name")
            if name:
                found[name] = os.path.dirname(path)
    return found


def imports_from_package_dir(directory: str) -> set[str]:
    out: set[str] = set()
    for ext in ("js", "mjs", "cjs"):
        for path in glob.glob(os.path.join(directory, "lib", "**", "*." + ext), recursive=True):
            try:
                text = open(path, encoding="utf8", errors="ignore").read()
            except Exception:
                continue
            for spec in SPEC.findall(text):
                out.add("/".join(spec.split("/")[:2]))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: verify-app-deps.py <App.app> [repo-root]", file=sys.stderr)
        return 2
    app = sys.argv[1]
    repo = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    asar = os.path.join(app, "Contents", "Resources", "app.asar")
    if not os.path.isfile(asar):
        print(f"找不到 {asar}", file=sys.stderr)
        return 1

    entries, handle = load_asar(asar)
    packed: dict[str, list[tuple[str, int, int]]] = {}
    for path, (offset, size) in entries.items():
        match = re.match(r"^node_modules/@deepseek-ai/([^/]+)/", path)
        if match and path.endswith((".js", ".mjs", ".cjs")):
            packed.setdefault(match.group(1), []).append((path, offset, size))

    dirs = workspace_dirs(repo)
    seen: set[str] = set()
    missing: list[str] = []
    queue = [f"@deepseek-ai/{name}" for name in packed]

    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        short = name.split("/")[1]
        needed: set[str] = set()
        if short in packed:
            for _path, offset, size in packed[short]:
                handle.seek(offset)
                text = handle.read(size).decode("utf8", "ignore")
                needed |= {"/".join(s.split("/")[:2]) for s in SPEC.findall(text)}
        elif name in dirs:
            needed = imports_from_package_dir(dirs[name])
        for dep in needed:
            if not dep.startswith("@deepseek-ai/") or dep in seen:
                continue
            if dep.split("/")[1] not in packed and dep not in missing:
                missing.append(dep)
            queue.append(dep)

    print("产物内 shell @deepseek-ai 包:", ", ".join(sorted(packed)))
    if missing:
        print("产物缺少 shell 运行时依赖（传递闭包）:", ", ".join(sorted(missing)), file=sys.stderr)
        print("→ 把它们加进 config/patch-package-target.py 的 SHELL_RUNTIME_DEV_DEPS", file=sys.stderr)
        return 1
    print(f"依赖闭包完整 ✓（扫描 {len(seen)} 个包）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
