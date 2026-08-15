# 多战法扫描工具箱 — 全平台通用 Skill（可扩展）

A 股「多战法扫描」工具：用户说「根据战法扫描」时，先拉最新行情数据，按战法筛选"符合条件"的股票 + 操作注意事项。

## 当前战法
| 战法 | 触发词 | 脚本 |
|---|---|---|
| 突破战法（量价确认） | 突破战法 / 放量突破 / 扫突破的票 | `scripts/breakout_scanner.py` |
| 低吸战法（缩量回踩） | 低吸战法 / 缩量回踩 / 回踩低吸 / 强势股回调 | `scripts/pullback_scanner.py` |

**新增战法**：`references/` 加规则 + `scripts/` 加脚本 + `SKILL.md` 加触发词，跑 `sync-skills.sh`。

## 兼容矩阵

| Agent | 支持 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills/` |
| Claude Code | `CLAUDE.md` / `~/.claude/skills/` |
| Codex | `AGENTS.md` / `~/.codex/skills/` |
| Gemini | `GEMINI.md` / `~/.gemini/skills/` |
| Cursor / OpenCode / 其他 | 规则入口 + 开放标准 SKILL.md |
| 通用发现总线 | `.agents/skills/<name>/SKILL.md` |

## 安装
- `npx skills add <owner>/<repo>`（发布后）
- `scripts/install.sh`（macOS/Linux）/ `scripts/install.ps1`（Windows）
- 手动复制本目录到目标 agent 的 skills 目录

## 维护
- 只改根 `SKILL.md` + `references/`；改完 `scripts/sync-skills.sh`。
- 每次调用**实时取最新数据**，不用缓存。
