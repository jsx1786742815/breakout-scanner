#!/usr/bin/env bash
# 突破战法扫描 skill 安装脚本（macOS/Linux）
# 把本 skill 目录复制到已检测到的各 agent 个人 skills 目录。覆盖式复制，不用 rm -rf。
set -e
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

declare -A AGENTS=(
  [Claude]="$HOME/.claude/skills/breakout-scanner"
  [Codex]="$HOME/.codex/skills/breakout-scanner"
  [Gemini]="$HOME/.gemini/skills/breakout-scanner"
  [Cursor]="$HOME/.cursor/skills/breakout-scanner"
  [OpenCode]="$HOME/.config/opencode/skills/breakout-scanner"
  [通用总线]="$HOME/.agents/skills/breakout-scanner"
)

echo "源目录: $SRC"
for name in "${!AGENTS[@]}"; do
  dst="${AGENTS[$name]}"
  parent="$(dirname "$dst")"
  if [ -d "$parent" ]; then
    mkdir -p "$dst"
    cp -R "$SRC/." "$dst/"
    echo "[OK] $name -> $dst"
  else
    echo "[跳过] $name (未检测到 $parent)"
  fi
done
echo "安装完成。"
