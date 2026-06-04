# FastZoom Archaeological System - Setup Script (Docker only)
param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

# ============= CONFIGURAZIONE GLOBALE =============
$PROJECT_NAME    = "FastZoom Archaeological System"
$FASTAPI_PORT    = 8000
$MINIO_PORT      = 9000
$MINIO_CONSOLE_PORT = 9001

# ============= HELPER: verifica Docker =============
function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "❌ Docker non trovato. Installa Docker Desktop e riprova." -ForegroundColor Red
        exit 1
    }
}

# ============= HELPER: credenziali =============
function Show-Credentials {
    Write-Host ""
    Write-Host "🔐 Credenziali" -ForegroundColor Blue
    Write-Host "==============" -ForegroundColor Blue
    Write-Host "  App URL    : http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Cyan
    Write-Host "  Email      : superuser@admin.com" -ForegroundColor Yellow
    Write-Host "  Password   : password123" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  MinIO UI   : http://127.0.0.1:$MINIO_CONSOLE_PORT" -ForegroundColor Cyan
    Write-Host "  MinIO user : minioadmin" -ForegroundColor Yellow
    Write-Host "  MinIO pass : minioadmin" -ForegroundColor Yellow
    Write-Host ""
}

# ============= HELP =============
function Show-Help {
    Write-Host "================================================================" -ForegroundColor Blue
    Write-Host "      FastZoom Archaeological System - Setup Script (Docker)    " -ForegroundColor Blue
    Write-Host "================================================================" -ForegroundColor Blue
    Write-Host ""
    Write-Host "  run-dev      - Avvia in foreground con auto-reload (sviluppo)" -ForegroundColor Yellow
    Write-Host "  run          - Avvia in background / detached (produzione)" -ForegroundColor Yellow
    Write-Host "  stop         - Ferma tutti i container" -ForegroundColor Yellow
    Write-Host "  restart      - Ferma e riavvia i container" -ForegroundColor Yellow
    Write-Host "  build        - Rebuild dell'immagine Docker (no cache)" -ForegroundColor Yellow
    Write-Host "  logs         - Stream dei log in tempo reale" -ForegroundColor Yellow
    Write-Host "  logs-app     - Log solo del container app" -ForegroundColor Yellow
    Write-Host "  logs-minio   - Log solo di MinIO" -ForegroundColor Yellow
    Write-Host "  status       - Stato dei container" -ForegroundColor Yellow
    Write-Host "  shell        - Shell interattiva nel container app" -ForegroundColor Yellow
    Write-Host "  credentials  - Mostra credenziali di accesso" -ForegroundColor Yellow
    Write-Host "  clean        - Rimuove container, volumi e immagini del progetto" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Uso: .\setup.ps1 [comando]" -ForegroundColor White
    Write-Host ""
    Write-Host "Esempi:" -ForegroundColor Green
    Write-Host "  .\setup.ps1 run-dev    # sviluppo con auto-reload" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1 logs       # vedi i log live" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1 stop       # ferma tutto" -ForegroundColor Cyan
}

# ============= COMANDI =============

function Start-Dev {
    Assert-Docker
    Write-Host "🔧 Avvio in modalita SVILUPPO (foreground, auto-reload)..." -ForegroundColor Blue
    Write-Host "   Volumi: ./app -> /app/app  |  ./data -> /app/data" -ForegroundColor DarkCyan
    Write-Host ""
    Write-Host "  App     : http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Green
    Write-Host "  Swagger : http://127.0.0.1:$FASTAPI_PORT/docs" -ForegroundColor Cyan
    Write-Host "  MinIO   : http://127.0.0.1:$MINIO_CONSOLE_PORT" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Premi Ctrl+C per fermare." -ForegroundColor Yellow
    Write-Host ""
    Show-Credentials
    docker compose up --build
}

function Start-Prod {
    Assert-Docker
    Write-Host "🚀 Avvio in modalita PRODUZIONE (background)..." -ForegroundColor Blue
    docker compose up -d --build
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Container avviati." -ForegroundColor Green
        Write-Host "  App     : http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Cyan
        Write-Host "  MinIO   : http://127.0.0.1:$MINIO_CONSOLE_PORT" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Log : .\setup.ps1 logs" -ForegroundColor DarkGray
        Write-Host "  Stop: .\setup.ps1 stop" -ForegroundColor DarkGray
    }
}

function Stop-All {
    Assert-Docker
    Write-Host "🛑 Arresto container..." -ForegroundColor Blue
    docker compose down
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Container fermati." -ForegroundColor Green
    }
}

function Restart-All {
    Stop-All
    Start-Prod
}

function Build-Image {
    Assert-Docker
    Write-Host "📦 Rebuild immagine Docker (no cache)..." -ForegroundColor Blue
    docker compose build --no-cache
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Build completata." -ForegroundColor Green
    }
}

function Show-Logs {
    Assert-Docker
    Write-Host "📝 Log live (Ctrl+C per uscire)..." -ForegroundColor Blue
    docker compose logs -f
}

function Show-LogsApp {
    Assert-Docker
    Write-Host "📝 Log app (Ctrl+C per uscire)..." -ForegroundColor Blue
    docker compose logs -f app
}

function Show-LogsMinio {
    Assert-Docker
    Write-Host "📝 Log MinIO (Ctrl+C per uscire)..." -ForegroundColor Blue
    docker compose logs -f minio
}

function Show-Status {
    Assert-Docker
    Write-Host "📊 Stato container:" -ForegroundColor Blue
    docker compose ps
}

function Open-Shell {
    Assert-Docker
    Write-Host "🐚 Shell interattiva nel container app..." -ForegroundColor Blue
    docker compose exec app /bin/bash
}

function Clean-All {
    Assert-Docker
    Write-Host "🧹 Rimozione container, volumi e immagini del progetto..." -ForegroundColor Yellow
    Write-Host "   (i dati in ./data e ./app NON vengono cancellati)" -ForegroundColor DarkGray
    $confirm = Read-Host "Sei sicuro? [s/N]"
    if ($confirm -match "^[sS]$") {
        docker compose down -v --rmi local
        Write-Host "✅ Pulizia completata." -ForegroundColor Green
    } else {
        Write-Host "Operazione annullata." -ForegroundColor Yellow
    }
}

# ============= DISPATCH =============
switch ($Command.ToLower()) {
    "run-dev"     { Start-Dev }
    "run"         { Start-Prod }
    "stop"        { Stop-All }
    "restart"     { Restart-All }
    "build"       { Build-Image }
    "logs"        { Show-Logs }
    "logs-app"    { Show-LogsApp }
    "logs-minio"  { Show-LogsMinio }
    "status"      { Show-Status }
    "shell"       { Open-Shell }
    "credentials" { Show-Credentials }
    "clean"       { Clean-All }
    "help"        { Show-Help }
    default {
        Write-Host "❌ Comando sconosciuto: '$Command'" -ForegroundColor Red
        Write-Host ""
        Show-Help
    }
}
