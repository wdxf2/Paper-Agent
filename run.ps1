param(
    [string]$EnvName = "CrewAI",
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$condaCandidates = @(
    (Get-Command conda.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source),
    "D:\environment\Anaconda\Scripts\conda.exe",
    "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
    "$env:USERPROFILE\anaconda3\Scripts\conda.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$conda = $condaCandidates | Select-Object -First 1
if (-not $conda) {
    throw "未找到 conda。请先配置 conda，或修改本脚本中的 conda 路径。"
}

$env:PAPER_AGENT_HOST = $HostAddress
$env:PAPER_AGENT_PORT = "$Port"
& $conda run --no-capture-output -n $EnvName python -m uvicorn paper_review_agent.api:app --host $HostAddress --port $Port
