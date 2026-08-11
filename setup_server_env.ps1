$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$sshUser = "maestro"
$sshHost = "168.119.63.168"
$remoteEnvFile = "/etc/jaila-backend.env"

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

if (-not (Test-Path $env:SSH_KEY)) {
    Write-Host "SSH-nøgle mangler: $env:SSH_KEY"
    Write-Host ""
    Write-Host "Opret nøgle:"
    Write-Host "  ssh-keygen -t ed25519 -f `"$env:SSH_KEY`""
    Write-Host "Send den offentlige nøgle til server-admin, så den kan tilføjes for brugeren maestro."
    exit 1
}

if (-not $env:OPENAI_API_KEY) {
    Write-Host "Mangler OPENAI_API_KEY i .env"
    exit 1
}

if (-not $env:SUDO_PASS) {
    Write-Host "Mangler SUDO_PASS i .env"
    exit 1
}

$frontendOrigins = if ($env:FRONTEND_ORIGINS) {
    $env:FRONTEND_ORIGINS
} else {
    "https://skat-chat.dk"
}

$envContent = @(
    "OPENAI_API_KEY=$($env:OPENAI_API_KEY)"
    "FRONTEND_ORIGINS=$frontendOrigins"
) -join "`n"

$tempFile = Join-Path $env:TEMP "jaila-backend.env"
Set-Content -Path $tempFile -Value $envContent -NoNewline -Encoding utf8

Write-Host "Uploader miljøfil til server..."
scp -i $env:SSH_KEY $tempFile "${sshUser}@${sshHost}:~/jaila-backend.env"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installerer $remoteEnvFile og genstarter backend..."
$remoteCmd = @(
    "echo $($env:SUDO_PASS) | sudo -S install -m 600 -o root -g root ~/jaila-backend.env $remoteEnvFile"
    "echo $($env:SUDO_PASS) | sudo -S systemctl restart jaila-backend"
    "echo $($env:SUDO_PASS) | sudo -S systemctl is-active jaila-backend"
) -join " && "

ssh -i $env:SSH_KEY "${sshUser}@${sshHost}" $remoteCmd
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Remove-Item $tempFile -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Verificerer produktion..."
try {
    $health = Invoke-RestMethod -Uri "https://skat-chat.dk/api/health" -TimeoutSec 15
    Write-Host "Health: $($health.status)"
} catch {
    Write-Host "Kunne ikke hente /api/health: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Faerdig. Serveren koerer nu med API-noeglen i $remoteEnvFile"
