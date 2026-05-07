#!/bin/bash
# Shell script to start Flask application for API Test Command Center

echo "Starting Flask application for API Test Command Center..."
echo ""
echo "Server will be available at: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if required packages are installed
echo "Checking required packages..."
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Flask is not installed. Installing required packages..."
    pip install -r requirements.txt
fi

# Start Flask application
echo ""
echo "Starting Flask server..."
python3 start_flask_no_debug.py

if [ $? -ne 0 ]; then
    echo "Failed to start Flask application"
    exit 1
fi