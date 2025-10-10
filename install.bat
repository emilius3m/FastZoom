@echo off
echo 🏺 FastZoom Archaeological System - Dependency Installer
echo ========================================================
echo.

echo 🔄 Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

echo 🐍 Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo ❌ Failed to create virtual environment
        pause
        exit /b 1
    )
    echo ✅ Virtual environment created successfully!
) else (
    echo ⚠️ Virtual environment already exists
)

echo 🔄 Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ Failed to activate virtual environment
    pause
    exit /b 1
)

echo 📦 Installing dependencies with pip...
echo.

REM Core dependencies (matching corrected pyproject.toml)
set "deps=fastapi==0.115.14 uvicorn==0.35.0 sqlalchemy==2.0.41 alembic==1.16.2 aiosqlite==0.19.0 pydantic==2.11.7 pydantic-settings==2.2.1 jinja2==3.1.6 python-multipart==0.0.9 pillow==10.0.0 minio==7.2.7 fastapi-csrf-protect==1.0.3 fastapi-users[sqlalchemy]==14.0.1 httpx==0.28.1 nh3==0.2.21 jsonschema==4.23.0 bcrypt==4.0.1 python-dotenv==1.0.0 loguru==0.7.2"

echo Installing: %deps%
echo.

pip install %deps%
if errorlevel 1 (
    echo ❌ Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo 🎉 All dependencies installed successfully!
echo 🚀 You can now run the application with:
echo    python main.py
echo    or
echo    uvicorn app.app:app --reload --host 0.0.0.0 --port 8000
echo.
echo Press any key to continue...
pause >nul