# Launching Flask Application for API Test Command Center

This guide explains how to launch the Flask application for the API Test Command Center from the terminal.

## Prerequisites

1. **Python 3.7+** installed on your system
2. **Required Python packages** (install using `pip install -r requirements.txt`)

## Quick Start Methods

### Method 1: Using Batch File (Windows)
```bash
# Double-click the file or run from command prompt:
start_flask.bat
```

### Method 2: Using Shell Script (Linux/Mac)
```bash
# Make the script executable (first time only)
chmod +x start_flask.sh

# Run the script
./start_flask.sh
```

### Method 3: Direct Python Command
```bash
# From the project root directory:
python start_flask_no_debug.py
```

### Method 4: Direct Flask Run (Alternative)
```bash
# Using Python directly:
python -c "from app import app; app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)"
```

## What Happens When You Start Flask

1. **Server starts** on `http://localhost:5000`
2. **API endpoints** become available:
   - `GET /` - Web interface
   - `POST /api/generate` - Generate test cases
   - `POST /api/export-excel` - Export to Excel
   - `POST /api/save-to-database` - Save to database
   - `GET /api/database-sessions` - View saved sessions
   - `GET /api/database-test-cases/<session_id>` - View test cases

3. **Database connection** is established (if SQL Server is available)
4. **Dynamic tables** are created as needed based on URL patterns

## Stopping the Server

Press **Ctrl+C** in the terminal where Flask is running.

## Troubleshooting

### Port 5000 Already in Use
If you get an error that port 5000 is already in use:
```bash
# Option 1: Kill the process using port 5000 (Windows)
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Option 2: Use a different port
python start_flask_no_debug.py --port 5001
```

### Database Connection Issues
If database connection fails:
1. Ensure SQL Server is running
2. Check Windows Authentication is enabled
3. Verify database `API_Test_Cases` exists

### Missing Dependencies
If you get import errors:
```bash
pip install -r requirements.txt
```

## Advanced Options

### Run with Debug Mode (Development)
```bash
# Edit start_flask_no_debug.py and change debug=False to debug=True
# Or run directly:
python -c "from app import app; app.run(debug=True, host='0.0.0.0', port=5000)"
```

### Run on Different Host/Port
```bash
python -c "from app import app; app.run(debug=False, host='127.0.0.1', port=8080, use_reloader=False)"
```

## Verification

After starting Flask, verify it's running by:
1. Opening a browser to `http://localhost:5000`
2. Checking the API health endpoint: `http://localhost:5000/api/health`
3. Testing database connection: `http://localhost:5000/api/database-health`

## Notes

- The application uses **Windows Authentication** for SQL Server
- Test cases are saved to **dynamic tables** based on URL patterns
- Excel export and database save now have **identical data** (status codes are extracted the same way)