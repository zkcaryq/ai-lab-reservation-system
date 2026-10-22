# 一键重新部署（在 Windows 本机运行）
#
#   .\deploy\redeploy.ps1              # 重新构建前端 + 上传 + 服务器重建镜像并重启
#   .\deploy\redeploy.ps1 -SkipFrontend # 只改了后端时，跳过 npm 构建
#
# 前置条件：本机已配置 SSH 别名 aliyun（见 ~/.ssh/config），npm 可用。

param(
    [string]$Alias = 'aliyun',
    [string]$RemoteDir = '/opt/ai-lab',
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP 'ai-lab-deploy'
$remoteStage = '/tmp/ai-lab-deploy'

Write-Host "[1/5] 构建前端（同源配置 .env.production）" -ForegroundColor Cyan
if (-not $SkipFrontend) {
    Push-Location (Join-Path $root 'frontend/front_agent')
    try { npm run build } finally { Pop-Location }
} else {
    Write-Host '      已跳过' -ForegroundColor DarkGray
}

Write-Host "[2/5] 打包源码与静态资源" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $stage | Out-Null
tar -czf "$stage\backend.tgz" `
    --exclude "backend/.venv" `
    --exclude "backend/__pycache__" `
    --exclude "backend/.ruff_cache" `
    --exclude "backend/.idea" `
    --exclude "backend/.workbuddy" `
    --exclude "backend/logs" `
    --exclude "backend/uploads" `
    --exclude "backend/storage" `
    --exclude "backend/.env" `
    -C $root backend
tar -czf "$stage\dist.tgz" -C (Join-Path $root 'frontend/front_agent') dist

Write-Host "[3/5] 上传到服务器 $remoteStage" -ForegroundColor Cyan
ssh -o BatchMode=yes $Alias "rm -rf $remoteStage && mkdir -p $remoteStage"
scp "$stage\backend.tgz" "$stage\dist.tgz" "${Alias}:$remoteStage/"

Write-Host "[4/5] 服务器上替换代码并重建镜像" -ForegroundColor Cyan
$remoteScript = @"
set -e
[ -d $RemoteDir ] || { echo '目标目录不存在: $RemoteDir'; exit 1; }
cd $RemoteDir
echo '--- 替换 backend ---'
rm -rf backend
tar -xzf $remoteStage/backend.tgz -C $RemoteDir
echo '--- 替换 web/dist ---'
rm -rf web/dist
tar -xzf $remoteStage/dist.tgz -C $RemoteDir/web
chmod -R a+rX web/dist
echo '--- 构建镜像 ---'
docker compose build api
echo '--- 重启容器 ---'
docker compose up -d
rm -rf $remoteStage
"@
$remoteScript | ssh -o BatchMode=yes $Alias "bash -s"

Write-Host "[5/5] 健康检查" -ForegroundColor Cyan
$health = ssh -o BatchMode=yes $Alias "sleep 6; curl -fsS -m 10 http://127.0.0.1/health/ready"
Write-Host "      $health"
Write-Host '部署完成：http://39.104.226.135/' -ForegroundColor Green
