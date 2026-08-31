$ErrorActionPreference = "Stop"

$dockerOs = docker info --format '{{.OSType}}'
if ($dockerOs.Trim() -ne "linux") {
    throw "Docker Desktop Linux containers modunda olmalıdır."
}

if (-not (ollama list | Select-String -SimpleMatch "qwen3:4b")) {
    throw "qwen3:4b modeli bulunamadı. Önce 'ollama pull qwen3:4b' çalıştırın."
}

docker compose up --build --detach

for ($attempt = 1; $attempt -le 90; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8080/health" -TimeoutSec 5
        if ($health.status -eq "ok" -and $health.ollama -eq "ready") {
            Write-Host "BelgeDoğrula hazır: http://localhost:8080"
            exit 0
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}

docker compose ps
docker compose logs --tail 100
throw "Servisler üç dakika içinde hazır duruma gelmedi."
