$ErrorActionPreference = "Stop"

$NasriHome = if ($env:NASRI_HOME) { $env:NASRI_HOME } else { Join-Path $HOME ".nasri" }
$NasriSrc = Join-Path $NasriHome "src"
$NasriVenv = Join-Path $NasriHome "venv"
$NasriData = Join-Path $NasriHome "data"
$RepoUrl = if ($env:NASRI_REPO_URL) { $env:NASRI_REPO_URL } else { "https://github.com/feyzeddin/nasri-local-ai.git" }

New-Item -ItemType Directory -Force -Path $NasriHome | Out-Null
New-Item -ItemType Directory -Force -Path $NasriData | Out-Null

if (Test-Path (Join-Path $NasriSrc ".git")) {
  git -C $NasriSrc fetch origin main
  git -C $NasriSrc pull --ff-only origin main
} else {
  git clone $RepoUrl $NasriSrc
}

if (-not (Test-Path $NasriVenv)) {
  python -m venv $NasriVenv
}

$Py = Join-Path $NasriVenv "Scripts\python.exe"
$NasriExe = Join-Path $NasriVenv "Scripts\nasri.exe"

& $Py -m pip install --upgrade pip
& $Py -m pip install -e (Join-Path $NasriSrc "project\nasri-core")

[Environment]::SetEnvironmentVariable("NASRI_INSTALL_DIR", $NasriSrc, "User")
$env:NASRI_INSTALL_DIR = $NasriSrc
[Environment]::SetEnvironmentVariable("NASRI_DATA_DIR", $NasriData, "User")
$env:NASRI_DATA_DIR = $NasriData

$BinDir = Join-Path $NasriHome "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$CmdPath = Join-Path $BinDir "nasri.cmd"
@"
@echo off
set NASRI_INSTALL_DIR=$NasriSrc
set NASRI_DATA_DIR=$NasriData
"$NasriExe" %*
"@ | Set-Content -Encoding ASCII $CmdPath

$CurrentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($CurrentUserPath -notlike "*$BinDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$CurrentUserPath;$BinDir", "User")
}

& $NasriExe install-service

Write-Host "Kurulum tamamlandi."
Write-Host "Yeni terminal acip komutlari kullanabilirsin: nasri /status | nasri /version | nasri /help"
