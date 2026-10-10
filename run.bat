@echo off
setlocal
echo.
echo ===================================================
echo   DocQA Studio - Enterprise RAG Platform
echo ===================================================
echo.

REM 1. Verify Python Installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please download and install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

REM 2. Ensure virtual environment exists
if not exist "venv" (
    echo [*] Creating virtual environment (venv)...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM 3. Activate virtual environment
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

REM 4. Verify & install dependencies
echo [*] Checking dependencies from requirements.txt...
pip install -r requirements.txt -q

REM 5. Check configuration
if not exist ".env" (
    if exist ".env.example" (
        echo [*] Initializing .env from .env.example...
        copy .env.example .env >nul
    )
    echo [NOTICE] Please edit .env and ensure your GROQ_API_KEY is configured.
)

REM 6. Launch Application
echo.
echo [*] Launching DocQA Studio server...
echo ===================================================
echo   URL: http://localhost:5000
echo   Press Ctrl+C to terminate
echo ===================================================
echo.

python app.py

pause
