# 突破战法扫描 skill 安装脚本（Windows PowerShell 5.1 兼容）
# 作用：把本 skill 目录复制到已检测到的各 agent 个人 skills 目录。
# 注意：只用覆盖式复制（Copy-Item -Recurse -Force），不用 Remove-Item -Recurse（会被安全策略拦截）。

$ErrorActionPreference = 'Stop'
$src = Split-Path -Parent $PSScriptRoot   # skill 根目录

$agents = @{
    'Claude Code' = "$env:USERPROFILE\.claude\skills\breakout-scanner"
    'Codex'       = "$env:USERPROFILE\.codex\skills\breakout-scanner"
    'Gemini'      = "$env:USERPROFILE\.gemini\skills\breakout-scanner"
    'Cursor'      = "$env:USERPROFILE\.cursor\skills\breakout-scanner"
    'OpenCode'    = "$env:USERPROFILE\.config\opencode\skills\breakout-scanner"
    '通用总线'     = "$env:USERPROFILE\.agents\skills\breakout-scanner"
    'WorkBuddy'   = "$env:USERPROFILE\.workbuddy\skills\breakout-scanner"
}

Write-Host "源目录: $src"
foreach ($name in $agents.Keys) {
    $dst = $agents[$name]
    # 只有父目录已存在（说明装了该 agent）才安装
    $parent = Split-Path -Parent $dst
    if (Test-Path $parent) {
        if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }
        Copy-Item -Path "$src\*" -Destination $dst -Recurse -Force
        Write-Host "[OK] $name -> $dst"
    } else {
        Write-Host "[跳过] $name (未检测到 $parent)"
    }
}
Write-Host "安装完成。"
