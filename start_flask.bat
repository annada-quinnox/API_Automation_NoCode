@echo off
REM Batch file to start Flask application for API Test Command Center
echo Starting Flask application for API Test Command Center...
echo.
echo Server will be available at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if required packages are installed
echo Checking required packages...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Flask is not installed. Installing required packages...
    pip install -r requirements.txt
)

REM Start Flask application
echo.
echo Starting Flask server...
python start_flask_no_debug.py

if errorlevel 1 (
    echo Failed to start Flask application
    pause
)