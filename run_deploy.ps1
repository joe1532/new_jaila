$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
        }
    }
}

if (-not $env:SSH_KEY) {
    $env:SSH_KEY = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
}

if (-not $env:SUDO_PASS) {
    Write-Host "Mangler SUDO_PASS i .env"
    exit 1
}

if (-not (Test-Path $env:SSH_KEY)) {
    Write-Host "SSH-nøgle mangler: $env:SSH_KEY"
    Write-Host "Du skal have adgang som maestro@168.119.63.168 (spørg om nøglen eller opret en ny)."
    exit 1
}

Write-Host "Deployer JAILA til server (sudo via .env)..."
cmd /c "set SUDO_PASS=$env:SUDO_PASS&& set SSH_KEY=$env:SSH_KEY&& call DEPLOY_ALL.bat"
