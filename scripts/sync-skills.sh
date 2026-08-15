#!/usr/bin/env bash
# 同步根 SKILL.md + references/ → .agents/skills/breakout-scanner/（覆盖式复制，禁用 rm -rf）
set -e
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="$SRC/.agents/skills/breakout-scanner"

mkdir -p "$DST/references"
cp "$SRC/SKILL.md" "$DST/SKILL.md"
cp "$SRC/AGENTS.md" "$DST/AGENTS.md"
cp "$SRC/CLAUDE.md" "$DST/CLAUDE.md"
cp "$SRC/GEMINI.md" "$DST/GEMINI.md"
cp "$SRC/README.md" "$DST/README.md"
cp -R "$SRC/references/." "$DST/references/"
cp -R "$SRC/scripts/." "$DST/scripts/"

echo "已同步 → $DST"
# 验证
if diff -q "$SRC/SKILL.md" "$DST/SKILL.md" >/dev/null 2>&1; then
  echo "[OK] SKILL.md 同步一致"
else
  echo "[警告] SKILL.md 与副本不一致"
fi
