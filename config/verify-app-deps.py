#!/usr/bin/env python3
"""校验打出来的 .app 里，shell（Electron 主进程）运行时依赖是否齐全。

背景：上游 `apps/desktop/package.json` 把 `@deepseek-ai/dsh-home-paths` /
`dsh-app-boot` / `dsh-deepseek-account` 声明成 **devDependencies**，而 shell 的
`lib/main.js`（tsdown 产物、`@deepseek-ai/*` 保持 external）在运行时 import 它们；
electron-builder 只收集 **dependencies** → 产物缺包 → 一启动就弹
"A JavaScript error occurred in the main process: ERR_MODULE_NOT_FOUND"。

CI 里已用 `config/patch-package-target.py` 把它们挪进 dependencies；这里再校验一次
**结果**（断言后果，而不是断言"补丁跑过了"）。

用法：python3 config/verify-app-deps.py "/path/to/DeepSeek Harness (RC).app"
"""
from __future__ import annotations

import json
import os
import struct
import sys

REQUIRED = [
    "node_modules/@deepseek-ai/dsh-home-paths/package.json",
    "node_modules/@deepseek-ai/dsh-app-boot/package.json",
    "node_modules/@deepseek-ai/dsh-deepseek-account/package.json",
]


def asar_paths(asar: str) -> set[str]:
    with open(asar, "rb") as handle:
        head = handle.read(16)
        json_length = struct.unpack("<I", head[12:16])[0]
        header = json.loads(handle.read(json_length).decode("utf8"))

    found: set[str] = set()

    def walk(node: dict, prefix: str = "") -> None:
        for name, child in (node.get("files") or {}).items():
            path = prefix + name
            if "files" in child:
                walk(child, path + "/")
            else:
                found.add(path)

    walk(header)
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: verify-app-deps.py <App.app>", file=sys.stderr)
        return 2
    app = sys.argv[1]
    asar = os.path.join(app, "Contents", "Resources", "app.asar")
    if not os.path.isfile(asar):
        print(f"找不到 {asar}", file=sys.stderr)
        return 1

    paths = asar_paths(asar)
    missing = [item for item in REQUIRED if item not in paths]
    unpacked = sorted(p.replace("node_modules/@deepseek-ai/", "").split("/package.json")[0]
                      for p in paths
                      if p.startswith("node_modules/@deepseek-ai/") and p.endswith("/package.json"))
    print("app.asar 内的 shell @deepseek-ai 包:", ", ".join(unpacked) or "(空)")
    if missing:
        print("产物缺少 shell 运行时依赖：", ", ".join(m.split('/')[2] for m in missing), file=sys.stderr)
        print("→ 检查 config/patch-package-target.py 的 promote_runtime_dev_deps 是否生效", file=sys.stderr)
        return 1
    print("产物依赖完整 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
