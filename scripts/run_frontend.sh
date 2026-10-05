#!/usr/bin/env bash
# Flutter Web 启动脚本：运行日志规范化落到 ./logs/frontend/
#
# Web 端无法写本地盘，flutter run 的构建/运行输出由此脚本 tee 到
# logs/frontend/flutter_run.log（控制台同步可见）。
#
# 用法:
#   bash scripts/run_frontend.sh
#   FLUTTER_BIN=/path/to/flutter bash scripts/run_frontend.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/logs/frontend"

FLUTTER_BIN="${FLUTTER_BIN:-/c/flutter/bin/flutter}"
cd "$ROOT/app"

"$FLUTTER_BIN" run -d edge --web-port=8080 2>&1 |
  tee -a "$ROOT/logs/frontend/flutter_run.log"
