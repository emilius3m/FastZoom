param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

# ============= CONFIGURAZIONE GLOBALE =============
$PROJECT_NAME = "FastAPI-HTMX Archaeological System"
$FASTAPI_PORT = 8000
$MINIO_PORT = 9000
$MINIO_CONSOLE_PORT = 9001

# ============= CONFIGURAZIONE MINIO =============
$MINIO_DIR = "C:\minio"
$MINIO_EXE = "$MINIO_DIR\minio.exe"
$MC_EXE = "$MINIO_DIR\mc.exe"
$MINIO_DATA_DIR = "$MINIO_DIR\Data"
$MINIO_ROOT_USER = "minioadmin123456789"
$MINIO_ROOT_PASSWORD = "miniosecret987654321xyz"
$ARCHAEOLOGICAL_BUCKET = "archaeological-photos"
$MINIO_DOWNLOAD_URL = "https://dl.min.io/server/minio/release/windows-amd64/minio.exe"
$MC_DOWNLOAD_URL = "https://dl.min.io/client/mc/release/windows-amd64/mc.exe"

function Show-Help {
    Write-Host "================================================================" -ForegroundColor Blue
    Write-Host "        FastAPI-HTMX Archaeological System - Setup Script      " -ForegroundColor Blue  
    Write-Host "================================================================" -ForegroundColor Blue
    Write-Host ""
    Write-Host "🏺 FastAPI Commands:" -ForegroundColor Green
    Write-Host "  setup           - Complete project setup (FastAPI + MinIO)" -ForegroundColor Yellow
    Write-Host "  install         - Install Python dependencies only" -ForegroundColor Yellow
    Write-Host "  env             - Create .env configuration file" -ForegroundColor Yellow
    Write-Host "  migrate         - Run database migrations" -ForegroundColor Yellow
    Write-Host "  init-db         - Initialize database with migrations" -ForegroundColor Yellow
    Write-Host "  populate-db     - populate database with migrations" -ForegroundColor Yellow
    Write-Host "  run             - Start the FastAPI application" -ForegroundColor Yellow
    Write-Host "  run-dev         - Start in development mode with auto-reload" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "🏛️ MinIO Commands (Archaeological Storage):" -ForegroundColor Cyan
    Write-Host "  minio-install   - Download and install MinIO + MC client" -ForegroundColor Yellow
    Write-Host "  minio-start     - Start MinIO server" -ForegroundColor Yellow
    Write-Host "  minio-stop      - Stop MinIO server" -ForegroundColor Yellow
    Write-Host "  minio-setup     - Setup MinIO with archaeological buckets" -ForegroundColor Yellow
    Write-Host "  minio-status    - Check MinIO server status" -ForegroundColor Yellow
    Write-Host "  minio-console   - Open MinIO web console" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "ℹ️  Info Commands:" -ForegroundColor Magenta
    Write-Host "  credentials     - Show admin login credentials" -ForegroundColor Yellow
    Write-Host "  status          - Show project status" -ForegroundColor Yellow
    Write-Host "  clean           - Clean up generated files" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Usage: .\setup.ps1 [command]" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\setup.ps1 setup          # Complete setup" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1 run-dev        # Start development server" -ForegroundColor Cyan
    Write-Host "  .\setup.ps1 minio-start    # Start MinIO storage" -ForegroundColor Cyan
}

# ========== FUNZIONI FASTAPI ==========

function VirtualEnv {
    Write-Host "🐍 Creating Python virtual environment..." -ForegroundColor Blue
    if (-not (Test-Path "venv")) {
        try {
            python -m venv venv
            Write-Host "✅ Virtual environment created successfully!" -ForegroundColor Green
        } catch {
            Write-Host "❌ Failed to create virtual environment: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "⚠️ Virtual environment already exists" -ForegroundColor Yellow
    }
    
    return (Activate-VirtualEnv)
}

function Activate-VirtualEnv {
    Write-Host "🔄 Activating virtual environment..." -ForegroundColor Cyan
    try {
        if (Test-Path "venv\Scripts\Activate.ps1") {
            & ".\venv\Scripts\Activate.ps1"
            Write-Host "✅ Virtual environment activated!" -ForegroundColor Green
            return $true
        } else {
            Write-Host "❌ Activation script not found" -ForegroundColor Red
            return $false
        }
    } catch {
        Write-Host "❌ Failed to activate virtual environment: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function EnsureVirtualEnv {
    if (-not (Test-Path "venv")) {
        Write-Host "🐍 Virtual environment not found. Creating..." -ForegroundColor Blue
        return (Create-VirtualEnv)
    }
    
    if (-not $env:VIRTUAL_ENV) {
        return (Activate-VirtualEnv)
    }
    
    Write-Host "✅ Virtual environment already active" -ForegroundColor Green
    return $true
}

function Install-Dependencies {
    Write-Host "📦 Installing Python dependencies..." -ForegroundColor Blue

    if (-not (EnsureVirtualEnv)) {
        Write-Host "❌ Cannot proceed without virtual environment" -ForegroundColor Red
        return $false
    }

    try {
        if (Get-Command poetry -ErrorAction SilentlyContinue) {
            Write-Host "Using Poetry for dependency management..." -ForegroundColor Cyan
            poetry install
        }
        elseif (Test-Path "requirements.txt") {
            Write-Host "Using pip with requirements.txt..." -ForegroundColor Cyan
            pip install -r requirements.txt
        }
        else {
            Write-Host "Installing basic FastAPI dependencies..." -ForegroundColor Cyan
            pip install fastapi uvicorn sqlalchemy alembic pydantic-settings python-multipart jinja2 pillow minio
        }

        Write-Host "✅ Dependencies installed successfully!" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "❌ Failed to install dependencies: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Run-Migrations {
    Write-Host "🗄️ Running database migrations..." -ForegroundColor Blue
    
    if (-not (EnsureVirtualEnv)) {
        return $false
    }
    
    # Verifica se Alembic è inizializzato
    if (-not (Test-Path "alembic.ini")) {
        Write-Host "❌ Alembic not initialized. Please run 'alembic init' first." -ForegroundColor Red
        return $false
    }
    
    $migrationsPath = "app\migrations\versions"
    
    # Crea directory migrations se non esiste
    if (-not (Test-Path $migrationsPath)) {
        New-Item -ItemType Directory -Path $migrationsPath -Force | Out-Null
    }
    
    # Verifica se esistono migrations
    $migrationFiles = Get-ChildItem -Path $migrationsPath -Filter "*.py" -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne "__init__.py" }
        
    if (-not $migrationFiles) {
            Write-Host "📋 Creating initial migration..." -ForegroundColor Cyan
            
            if (Get-Command poetry -ErrorAction SilentlyContinue) {
                poetry run alembic revision --autogenerate -m "Archaeological system initial migration"
            } else {
                alembic revision --autogenerate -m "Archaeological system initial migration"
        }
    }
        
        # Applica migrations
    Write-Host "⬆️ Applying migrations..." -ForegroundColor Cyan
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
            poetry run alembic upgrade head
    } else {
            alembic upgrade head
    }
        
    Write-Host "✅ Database migrations completed!" -ForegroundColor Green
    return $true
}
function CreateEnvFile {
    Write-Host "📝 Creating .env configuration file..." -ForegroundColor Blue
    
    if (Test-Path ".env") {
        Write-Host "⚠️ .env file already exists, skipping..." -ForegroundColor Yellow
        return $true
    }
    
    $envContent = @"
# Database Configuration
DATABASE_URL="sqlite+aiosqlite:///./archaeological_catalog.db"
SECRET_KEY="archaeological-site-secret-key-2025-very-secure"

# MinIO Configuration (Storage per le 10.000 immagini archeologiche)
MINIO_URL="http://localhost:9000"
MINIO_ACCESS_KEY="minioadmin123456789"
MINIO_SECRET_KEY="miniosecret987654321xyz"
MINIO_BUCKET="archaeological-photos"
MINIO_SECURE=false

# CSRF Protection
CSRF_SECRET_KEY="csrf-archaeological-protection-key-2025"
COOKIE_SAMESITE="lax"
COOKIE_SECURE=false

# Multi-Site Archaeological Configuration
SITE_SELECTION_ENABLED=true
DEFAULT_SITE_REDIRECT=true
JWT_MULTI_SITE_ENABLED=true
JWT_EXPIRES_HOURS=24

# Storage Fotografico
MAX_PHOTO_SIZE_MB=50
SUPPORTED_FORMATS="jpg,jpeg,png,tiff,raw"
THUMBNAIL_SIZES="200,800"
AUTO_METADATA_EXTRACTION=true

# Sistema Museale
MUSEUM_NAME="Direzione Regionale Museale"
MUSEUM_CODE="DRM-2025"
BACKUP_RETENTION_DAYS=365
CATALOG_VERSION="1.0"
"@
    
    try {
        $envContent | Out-File -FilePath ".env" -Encoding UTF8
        Write-Host "✅ .env file created successfully!" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "❌ Failed to create .env file: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}


function Initialize-Database {
    Write-Host "Initializing database with migrations..." -ForegroundColor Blue
    
    # Check if alembic is initialized
    if (-not (Test-Path "alembic.ini")) {
        Write-Host "Alembic not initialized. Please run 'alembic init' first." -ForegroundColor Red
        return
    }
    
    # Create initial migration if none exist
    $migrationsPath = "app\migrations\versions"
    if (-not (Test-Path $migrationsPath)) {
        New-Item -ItemType Directory -Path $migrationsPath -Force | Out-Null
    }
    
    Run-Migrations
}

function Start-FastAPIApp {
    Write-Host "🚀 Starting FastAPI Archaeological System..." -ForegroundColor Blue
    
    if (-not (EnsureVirtualEnv)) {
        return $false
    }
    
    if (-not (Test-Path ".env")) {
        Write-Host "⚠️ .env file not found. Creating it..." -ForegroundColor Yellow
        Create-EnvFile
    }
    
    Write-Host ""
    Write-Host "🌐 Application will be available at: http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Green
    Write-Host "📱 Archaeological photo system ready!" -ForegroundColor Green
    Write-Host ""
    Show-Credentials
    
    try {
        if (Get-Command poetry -ErrorAction SilentlyContinue) {
            poetry run uvicorn app.app:app --host 127.0.0.1 --port $FASTAPI_PORT
        } else {
            uvicorn app.app:app --host 127.0.0.1 --port $FASTAPI_PORT
        }
    } catch {
        Write-Host "❌ Failed to start FastAPI: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Start-FastAPIAppDev {
    Write-Host "🔧 Starting FastAPI in DEVELOPMENT mode..." -ForegroundColor Blue
    
    if (-not (EnsureVirtualEnv)) {
        return $false
    }
    
    if (-not (Test-Path ".env")) {
        Write-Host "⚠️ .env file not found. Creating it..." -ForegroundColor Yellow
        Create-EnvFile
    }
    
    Write-Host ""
    Write-Host "🌐 Development server: http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Green
    Write-Host "🔄 Auto-reload enabled" -ForegroundColor Cyan
    Write-Host "📱 Archaeological system in development mode" -ForegroundColor Green
    Write-Host ""
    Show-Credentials
    
    try {
        if (Get-Command poetry -ErrorAction SilentlyContinue) {
            poetry run uvicorn app.app:app --reload --host 127.0.0.1 --port $FASTAPI_PORT
        } else {
            uvicorn app.app:app --reload --host 127.0.0.1 --port $FASTAPI_PORT
        }
    } catch {
        Write-Host "❌ Failed to start FastAPI in dev mode: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# ========== FUNZIONI MINIO (come definite prima) ==========

function Install-MinIO {
    Write-Host "🏺 Installing MinIO for Archaeological System..." -ForegroundColor Blue
    
    # Crea directory MinIO se non esiste
    if (-not (Test-Path $MINIO_DIR)) {
        New-Item -ItemType Directory -Path $MINIO_DIR -Force | Out-Null
        Write-Host "Created MinIO directory: $MINIO_DIR" -ForegroundColor Green
    }
    
    # Crea directory dati se non esiste  
    if (-not (Test-Path $MINIO_DATA_DIR)) {
        New-Item -ItemType Directory -Path $MINIO_DATA_DIR -Force | Out-Null
        Write-Host "Created MinIO data directory: $MINIO_DATA_DIR" -ForegroundColor Green
    }
    
    # Download MinIO server se non esiste
    if (-not (Test-Path $MINIO_EXE)) {
        Write-Host "Downloading MinIO server..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $MINIO_DOWNLOAD_URL -OutFile $MINIO_EXE -UseBasicParsing
            Write-Host "✅ MinIO server downloaded successfully!" -ForegroundColor Green
        } catch {
            Write-Host "❌ Failed to download MinIO server: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "MinIO server already installed" -ForegroundColor Yellow
    }
    
    # Download MinIO client se non esiste
    if (-not (Test-Path $MC_EXE)) {
        Write-Host "Downloading MinIO client (mc)..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $MC_DOWNLOAD_URL -OutFile $MC_EXE -UseBasicParsing
            Write-Host "✅ MinIO client downloaded successfully!" -ForegroundColor Green
        } catch {
            Write-Host "❌ Failed to download MinIO client: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "MinIO client already installed" -ForegroundColor Yellow
    }
    
    Write-Host "🎉 MinIO installation completed!" -ForegroundColor Green
    return $true
}

function Start-MinIOServer {
    Write-Host "🚀 Starting MinIO server for Archaeological System..." -ForegroundColor Blue
    
    # Verifica installazione
    if (-not (Test-Path $MINIO_EXE)) {
        Write-Host "❌ MinIO not installed. Run: .\setup.ps1 minio-install" -ForegroundColor Red
        return $false
    }
    
    # Verifica se già in esecuzione
    $minioProcess = Get-Process -Name "minio" -ErrorAction SilentlyContinue
    if ($minioProcess) {
        Write-Host "⚠️ MinIO server already running (PID: $($minioProcess.Id))" -ForegroundColor Yellow
        return $true
    }
    
    # Avvia server
    Push-Location $MINIO_DIR
    try {
        Write-Host "Starting MinIO server with archaeological configuration..." -ForegroundColor Cyan
        
        $env:MINIO_ROOT_USER = $MINIO_ROOT_USER
        $env:MINIO_ROOT_PASSWORD = $MINIO_ROOT_PASSWORD
        
        Start-Process -NoNewWindow -FilePath $MINIO_EXE -ArgumentList "server $MINIO_DATA_DIR --console-address :$MINIO_CONSOLE_PORT"
        
        Write-Host "⏳ Waiting for MinIO server to start (15 seconds)..." -ForegroundColor Cyan
        Start-Sleep -Seconds 15
        
        # Verifica avvio
        $minioCheck = Get-Process -Name "minio" -ErrorAction SilentlyContinue
        if ($minioCheck) {
            Write-Host "✅ MinIO server started successfully!" -ForegroundColor Green
            Write-Host "📍 API Endpoint: http://localhost:$MINIO_PORT" -ForegroundColor Cyan
            Write-Host "🎛️ Web Console: http://localhost:$MINIO_CONSOLE_PORT" -ForegroundColor Cyan
            Write-Host "👤 Username: $MINIO_ROOT_USER" -ForegroundColor Cyan
            Write-Host "🔑 Password: $MINIO_ROOT_PASSWORD" -ForegroundColor Cyan
            return $true
        } else {
            Write-Host "❌ Failed to start MinIO server" -ForegroundColor Red
            return $false
        }
        
    } catch {
        Write-Host "❌ Error starting MinIO: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    } finally {
        Pop-Location
    }
}

function Stop-MinIOServer {
    Write-Host "🛑 Stopping MinIO server..." -ForegroundColor Blue
    
    $minioProcess = Get-Process -Name "minio" -ErrorAction SilentlyContinue
    if ($minioProcess) {
        try {
            $minioProcess | Stop-Process -Force
            Write-Host "✅ MinIO server stopped successfully!" -ForegroundColor Green
            return $true
        } catch {
            Write-Host "❌ Failed to stop MinIO server: $($_.Exception.Message)" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "⚠️ MinIO server is not running" -ForegroundColor Yellow
        return $true
    }
}

function SetupMinIOBuckets {
    Write-Host "🏛️ Setting up archaeological buckets in MinIO..." -ForegroundColor Blue
    
    # Verifica che MinIO sia in esecuzione
    $minioProcess = Get-Process -Name "minio" -ErrorAction SilentlyContinue
    if (-not $minioProcess) {
        Write-Host "❌ MinIO server not running. Starting it first..." -ForegroundColor Red
        if (-not (Start-MinIOServer)) {
            return $false
        }
    }
    
    Push-Location $MINIO_DIR
    try {
        # Configura alias mc
        Write-Host "Configuring MinIO client..." -ForegroundColor Cyan
        & $MC_EXE alias set local http://localhost:$MINIO_PORT $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD
        
        # Verifica connessione
        Write-Host "Testing connection..." -ForegroundColor Cyan
        & $MC_EXE ls local
        
        # Crea bucket archeologici
        $buckets = @(
            $ARCHAEOLOGICAL_BUCKET,
            "archaeological-thumbnails", 
            "archaeological-metadata",
            "archaeological-reports"
        )
        
        foreach ($bucket in $buckets) {
            Write-Host "Creating bucket: $bucket" -ForegroundColor Cyan
            & $MC_EXE mb local/$bucket --ignore-existing
        }
        
        Write-Host "✅ Archaeological buckets setup completed!" -ForegroundColor Green
        Write-Host "📁 Main photos bucket: $ARCHAEOLOGICAL_BUCKET" -ForegroundColor Cyan
        
        return $true
        
    } catch {
        Write-Host "❌ Error setting up buckets: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    } finally {
        Pop-Location
    }
}

function Get-MinIOStatus {
    Write-Host "📊 MinIO Server Status" -ForegroundColor Blue
    Write-Host "======================" -ForegroundColor Blue
    
    # Verifica processo
    $minioProcess = Get-Process -Name "minio" -ErrorAction SilentlyContinue
    if ($minioProcess) {
        Write-Host "🟢 Status: RUNNING" -ForegroundColor Green
        Write-Host "🆔 Process ID: $($minioProcess.Id)" -ForegroundColor Cyan
        Write-Host "💾 Memory: $([math]::Round($minioProcess.WorkingSet / 1MB, 2)) MB" -ForegroundColor Cyan
        
        # Test connessione
        Push-Location $MINIO_DIR
        try {
            $buckets = & $MC_EXE ls local 2>$null
            if ($buckets) {
                Write-Host "📁 Buckets:" -ForegroundColor Cyan
                Write-Host $buckets
            }
        } catch {
            Write-Host "⚠️ Cannot connect to server" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
        
    } else {
        Write-Host "🔴 Status: STOPPED" -ForegroundColor Red
    }
    
    # Verifica installazione
    Write-Host ""
    Write-Host "📦 Installation:" -ForegroundColor Blue
    Write-Host "MinIO Server: $(if (Test-Path $MINIO_EXE) { '✅ Installed' } else { '❌ Not installed' })"
    Write-Host "MinIO Client: $(if (Test-Path $MC_EXE) { '✅ Installed' } else { '❌ Not installed' })"
    Write-Host "Data Directory: $(if (Test-Path $MINIO_DATA_DIR) { '✅ Exists' } else { '❌ Missing' })"
}

function Open-MinIOConsole {
    Write-Host "🎛️ Opening MinIO Web Console..." -ForegroundColor Blue
    
    $minioProcess = Get-Process -Name "minio" -ErrorAction SilentlyContinue
    if ($minioProcess) {
        Start-Process "http://localhost:$MINIO_CONSOLE_PORT"
        Write-Host "✅ MinIO console opened in browser" -ForegroundColor Green
        Write-Host "👤 Login with: $MINIO_ROOT_USER / $MINIO_ROOT_PASSWORD" -ForegroundColor Cyan
    } else {
        Write-Host "❌ MinIO server is not running. Start it first with: .\setup.ps1 minio-start" -ForegroundColor Red
    }
}

# ========== FUNZIONI UTILI ==========

function Show-Credentials {
    Write-Host ""
    Write-Host "🔐 Archaeological System Credentials" -ForegroundColor Blue
    Write-Host "====================================" -ForegroundColor Blue
    Write-Host "FastAPI Admin:" -ForegroundColor Cyan
    Write-Host "  Email: superuser@admin.com" -ForegroundColor Yellow
    Write-Host "  Password: password123" -ForegroundColor Yellow
    Write-Host "  URL: http://127.0.0.1:$FASTAPI_PORT" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "MinIO Storage:" -ForegroundColor Cyan
    Write-Host "  Console URL: http://localhost:$MINIO_CONSOLE_PORT" -ForegroundColor Yellow
    Write-Host "  Username: $MINIO_ROOT_USER" -ForegroundColor Yellow
    Write-Host "  Password: $MINIO_ROOT_PASSWORD" -ForegroundColor Yellow
    Write-Host ""
}

function Show-Status {
    if (-not (EnsureVirtualEnv)) {
        return $false
    }
    Write-Host "📊 Archaeological System Status" -ForegroundColor Blue
    Write-Host "===============================" -ForegroundColor Blue
    Write-Host "Project: $PROJECT_NAME" -ForegroundColor Blue
    Write-Host ""
    
    # Python Status
    try {
        $pythonVersion = python --version 2>$null
        Write-Host "🐍 Python: $pythonVersion" -ForegroundColor Green
    } catch {
        Write-Host "🐍 Python: ❌ Not found or not working" -ForegroundColor Red
    }
    
    # Virtual Environment
    if (Test-Path "venv") {
        Write-Host "📦 Virtual Environment: ✅ Exists" -ForegroundColor Green
        if ($env:VIRTUAL_ENV) {
            Write-Host "🔄 Virtual Environment: ✅ Active" -ForegroundColor Green
        } else {
            Write-Host "🔄 Virtual Environment: ⚠️ Not active" -ForegroundColor Yellow
        }
    } else {
        Write-Host "📦 Virtual Environment: ❌ Not found" -ForegroundColor Red
    }
    
    # Poetry Status
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
       $poetryVersion = poetry --version
       Write-Host "📚 Poetry: $poetryVersion" -ForegroundColor Green
    } else {
        Write-Host "📚 Poetry: ❌ Not found" -ForegroundColor Yellow
    }
    
    
    # Database Status
    try {
        if (Test-Path 'archaeological_catalog.db') {
            Write-Host "🗄️ Database: ✅ Exists (archaeological_catalog.db)" -ForegroundColor Green
        }
        elseif (Test-Path 'users.db') {
            Write-Host "🗄️ Database: ✅ Exists (users.db - legacy)" -ForegroundColor Yellow
        }
        else {
            Write-Host "🗄️ Database: ❌ Not found" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "⚠️ Errore verifica database: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    # Environment Configuration
    if (Test-Path '.env') {
        Write-Host "⚙️ Environment: ✅ Configured (.env exists)" -ForegroundColor Green
    } else {
        Write-Host "⚙️ Environment: ❌ Not configured" -ForegroundColor Red
    }
    
    # FastAPI Process Status
    $fastApiProcess = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { 
        $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*fastapi*" 
    }
    Write-Host "🌐 FastAPI Server: $(if ($fastApiProcess) { '🟢 Running' } else { '🔴 Stopped' })" -ForegroundColor $(if ($fastApiProcess) { 'Green' } else { 'Red' })
    
    Write-Host ""
    Get-MinIOStatus
}

function CleanProject {
    Write-Host "🧹 Cleaning up project files..." -ForegroundColor Blue
    
    # Python cache files
    Write-Host "Removing Python cache files..." -ForegroundColor Cyan
    Get-ChildItem -Recurse -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
    Get-ChildItem -Recurse -Directory -Name "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item $_ -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Test cache
    if (Test-Path ".pytest_cache") {
        Write-Host "Removing pytest cache..." -ForegroundColor Cyan
        Remove-Item ".pytest_cache" -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Temporary files
    Get-ChildItem -Filter "*.tmp" -ErrorAction SilentlyContinue | Remove-Item -Force
    
    Write-Host "✅ Cleanup completed!" -ForegroundColor Green
}

function Complete-Setup {
    Write-Host "🏺 Starting Complete Archaeological System Setup..." -ForegroundColor Blue
    Write-Host "==================================================" -ForegroundColor Blue
    Write-Host ""
    
    $success = $true
    
    # Step 1: FastAPI Environment
    Write-Host "STEP 1: Setting up Python environment..." -ForegroundColor Magenta
    if (-not (VirtualEnv)) { $success = $false }
    if (-not (Install-Dependencies)) { $success = $false }
    if (-not (Create-EnvFile)) { $success = $false }
    if (-not (Initialize-Database)) { $success = $false }
    
    # Step 2: MinIO Storage  
    Write-Host ""
    Write-Host "STEP 2: Setting up MinIO storage..." -ForegroundColor Magenta
    if (-not (Install-MinIO)) { $success = $false }
    if (-not (Start-MinIOServer)) { $success = $false }
    if (-not (Setup-MinIOBuckets)) { $success = $false }
    
    Write-Host ""
    if ($success) {
        Write-Host "🎉 ARCHAEOLOGICAL SYSTEM SETUP COMPLETED!" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "🌐 FastAPI App: http://localhost:$FASTAPI_PORT" -ForegroundColor Cyan
        Write-Host "🎛️ MinIO Console: http://localhost:$MINIO_CONSOLE_PORT" -ForegroundColor Cyan
        Write-Host "💾 Storage: $ARCHAEOLOGICAL_BUCKET bucket ready" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "🚀 Ready to catalog archaeological photos!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "  1. Run: .\setup.ps1 run-dev" -ForegroundColor Cyan
        Write-Host "  2. Open: http://localhost:$FASTAPI_PORT" -ForegroundColor Cyan
        Write-Host "  3. Login with the credentials above" -ForegroundColor Cyan
        Write-Host ""
        Show-Credentials
    } else {
        Write-Host "❌ Setup completed with errors. Check logs above." -ForegroundColor Red
    }
}

# ========== COMANDO SWITCH CORRETTO ==========
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "setup" { Complete-Setup }
    "install" { 
        if (-not (EnsureVirtualEnv)) { exit 1 }
        Install-Dependencies 
    }
    "env" { Create-EnvFile }
    "migrate" { 
        if (-not (EnsureVirtualEnv)) { exit 1 }
        Run-Migrations
    }
    "init-db" { 
        if (-not (EnsureVirtualEnv)) { exit 1 }
        Initialize-Database
    }
    "populate-db" { 
        if (-not (EnsureVirtualEnv)) { exit 1 }

    Write-Host "📊 Archaeological System Status" -ForegroundColor Blue
    Write-Host "===============================" -ForegroundColor Blue
    Write-Host "Project: $PROJECT_NAME" -ForegroundColor Blue
    Write-Host ""
    
    # Python Status
    try {
        python scripts/seed_archaeological_sites.py 
        
    } catch {
        Write-Host "🐍 Python: ❌ Not found or not working" -ForegroundColor Red
    }
    }
    "run" { 
        Start-FastAPIApp
    }
    "run-dev" { 
        Start-FastAPIAppDev
    }
    
    # MinIO Commands
    "minio-install" { Install-MinIO }
    "minio-start" { Start-MinIOServer }
    "minio-stop" { Stop-MinIOServer }
    "minio-setup" { Setup-MinIOBuckets }
    "minio-status" { Get-MinIOStatus }
    "minio-console" { Open-MinIOConsole }
    
    # Info Commands
    "credentials" { Show-Credentials }
    "status" { Show-Status }
    "clean" { Clean-Project }
    
    default { 
        Write-Host "❌ Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help 
    }
}
