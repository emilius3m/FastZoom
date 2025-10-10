#!/usr/bin/env python3
"""
FastZoom Dependency Installer
Bypasses Poetry and installs dependencies directly with pip
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and return success status"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed!")
        print(f"Error: {e.stderr}")
        return False

def main():
    print("🏺 FastZoom Archaeological System - Dependency Installer")
    print("=" * 60)

    # Check if Python is available
    if not run_command("python --version", "Checking Python installation"):
        print("❌ Python is not installed or not in PATH")
        sys.exit(1)

    # Create virtual environment if it doesn't exist
    if not os.path.exists("venv"):
        print("🐍 Creating virtual environment...")
        if not run_command("python -m venv venv", "Creating virtual environment"):
            sys.exit(1)

    # Activate virtual environment and install dependencies
    if os.name == 'nt':  # Windows
        activate_cmd = "venv\\Scripts\\activate"
        pip_cmd = "venv\\Scripts\\pip"
    else:  # Unix/Linux
        activate_cmd = "source venv/bin/activate"
        pip_cmd = "venv/bin/pip"

    print("📦 Installing dependencies with pip...")

    # Core dependencies (matching corrected pyproject.toml)
    dependencies = [
        "fastapi==0.115.14",
        "uvicorn==0.35.0",
        "sqlalchemy==2.0.41",
        "alembic==1.16.2",
        "aiosqlite==0.19.0",
        "pydantic==2.11.7",
        "pydantic-settings==2.2.1",
        "jinja2==3.1.6",
        "python-multipart==0.0.9",
        "pillow==11.3.0",
        "minio==7.2.7",
        "fastapi-csrf-protect==1.0.3",
        "fastapi-users[sqlalchemy]==14.0.1",
        "httpx==0.28.1",
        "nh3==0.2.21",
        "jsonschema==4.23.0",
        "bcrypt==4.0.1",
        "python-dotenv==1.0.0",
        "loguru==0.7.2"
    ]

    # Install each dependency
    for dep in dependencies:
        if not run_command(f"{pip_cmd} install {dep}", f"Installing {dep}"):
            print(f"❌ Failed to install {dep}")
            sys.exit(1)

    print("🎉 All dependencies installed successfully!")
    print("🚀 You can now run the application with:")
    print("   python main.py")
    print("   or")
    print("   uvicorn app.app:app --reload --host 0.0.0.0 --port 8000")

if __name__ == "__main__":
    main()