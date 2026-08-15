# AGENTS.md — 多战法扫描工具箱（可扩展）

## 这是什么
一个**全平台通用**的 A 股「多战法扫描」skill：用户说「根据战法扫描」时，先拉取**最新行情数据**，按对应战法筛选，输出符合条件的股票 + 操作注意事项（买点/止损/目标位/离场信号）。

## 当前战法（可扩展）
| 战法 | 触发词 | 脚本 |
|---|---|---|
| 突破战法（量价确认） | 突破战法/放量突破/扫突破的票 | scripts/breakout_scanner.py |
| 低吸战法（缩量回踩） | 低吸战法/缩量回踩/回踩低吸/强势股回调 | scripts/pullback_scanner.py |

**新增战法**：references/ 加规则 + scripts/ 加脚本 + SKILL.md 描述加触发词 + 跑 sync。

## 目录结构
```
SKILL.md                          # 唯一事实源（canonical）
AGENTS.md / CLAUDE.md / GEMINI.md # 各 agent 入口
README.md                         # 兼容矩阵 + 安装
references/
  ├── breakout-rules.md           # 突破战法规则
  └── pullback-rules.md           # 低吸战法规则
scripts/
  ├── breakout_scanner.py         # 突破扫描（取数+筛选）
  ├── pullback_scanner.py         # 低吸扫描（取数+筛选）
  ├── install.sh / install.ps1    # 安装到各 agent
  └── sync-skills.sh              # 同步 .agents 副本
```

## 核心工作流（每次先取最新数据）
1. 触发词路由到对应战法脚本。
2. 运行脚本（实时拉东财数据，不用缓存）→ 筛选 → 输出。
3. 输出必须含操作注意事项，不能只报代码。
4. 诚实提示：主力负/非主线/大盘未站上MA20/大盘高位 → 提示风险。

## 质量纪律
- 必须先取最新数据，禁止用旧结果/记忆冒充。
- 两个战法不混用（突破=追主升，低吸=埋伏）。
- 不做应声虫。

## 安装（多 agent）
- 通用：`npx skills add <owner>/<repo>`
- 脚本：`scripts/install.sh` / `scripts/install.ps1`（复制到已检测的 agent 目录）
- 手动：复制本目录到 `~/.claude/skills/`、`~/.codex/skills/`、`~/.gemini/skills/`、`~/.agents/skills/` 等。

## 维护规则
- 只改根 `SKILL.md` 和 `references/`，改完跑 `scripts/sync-skills.sh`。
- 入口文件只放摘要+指针，不复制全文。
