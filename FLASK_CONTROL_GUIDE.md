# Flask Control Guide: How to Stop and Launch Flask

This guide explains how to stop and launch the Flask application for the API Test Command Center.

## Quick Commands

### Check Flask Status
```bash
python flask_control.py status
```

### Stop Flask
```bash
python flask_control.py stop
```

### Start Flask
```bash
python flask_control.py start
```

### Restart Flask
```bash
python flask_control.py restart
```

## Detailed Methods

### Method 1: Using the Control Script (Recommended)

The `flask_control.py` script provides a unified way to manage Flask:

```bash
# Check if Flask is running
python flask_control.py status

# Stop Flask if it's running
python flask_control.py stop

# Start Flask with default settings
python flask_control.py start

# Start Flask on a different port
python flask_control.py start --port 8080

# Start Flask with debug mode
python flask_control.py start --debug

# Restart Flask (stop then start)
python flask_control.py restart
```

### Method 2: Manual Control

#### Stopping Flask Manually

**Option A: Press Ctrl+C in the terminal** where Flask is running (easiest method)

**Option B: Kill the process by PID** (if Flask is running in background):
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:5000 | xargs kill -9
```

**Option C: Use the batch/script files** (they handle Ctrl+C automatically)

#### Launching Flask Manually

**Option A: Using batch file (Windows)**:
```bash
start_flask.bat
```

**Option B: Using shell script (Linux/Mac)**:
```bash
chmod +x start_flask.sh  # First time only
./start_flask.sh
```

**Option C: Using Python launcher**:
```bash
python start_flask_no_debug.py
```

**Option D: Direct Python command**:
```bash
python -c "from app import app; app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)"
```

## Common Scenarios

### Scenario 1: Flask won't start (port already in use)
```bash
# Check what's using port 5000
python flask_control.py status

# If something else is using it, stop it
python flask_control.py stop

# Or start Flask on a different port
python flask_control.py start --port 5001
```

### Scenario 2: Flask started but can't access it
```bash
# Check if it's really running
python flask_control.py status

# Try accessing different URLs:
# - http://localhost:5000
# - http://127.0.0.1:5000
# - http://0.0.0.0:5000

# Check firewall settings
```

### Scenario 3: Need to restart Flask after code changes
```bash
# Quick restart
python flask_control.py restart

# Or manually:
python flask_control.py stop
python flask_control.py start
```

## Advanced Options

### Run on Specific Host and Port
```bash
python flask_control.py start --host 127.0.0.1 --port 8080
```

### Run with Debug Mode (Auto-reload on code changes)
```bash
python flask_control.py start --debug
```

### Run in Background (Linux/Mac)
```bash
./start_flask.sh &
```

### Run as Windows Service
```bash
# Create a scheduled task or use NSSM to run as service
start_flask.bat
```

## Verification Steps

After starting Flask, verify it's working:

1. **Check status**:
   ```bash
   python flask_control.py status
   ```

2. **Test web interface**:
   Open browser to: http://localhost:5000

3. **Test API health**:
   ```bash
   curl http://localhost:5000/api/health
   # Or open in browser: http://localhost:5000/api/health
   ```

4. **Test database connection** (if using database):
   ```bash
   curl http://localhost:5000/api/database-health
   ```

## Troubleshooting

### "Address already in use" Error
This means port 5000 is already being used:
```bash
# Find and kill the process
python flask_control.py stop

# Or use a different port
python flask_control.py start --port 5001
```

### "Module not found" Error
Missing Python packages:
```bash
pip install -r requirements.txt
```

### Flask starts but immediately stops
Check the error output in the terminal. Common issues:
- Database connection failed
- Missing configuration
- Syntax errors in code

### Can't access from other computers
By default, Flask binds to `0.0.0.0` (all interfaces). If you can't access from other computers:
1. Check firewall settings
2. Ensure Flask is binding to the correct IP
3. Try: `python flask_control.py start --host 0.0.0.0`

## Best Practices

1. **Always check status** before starting/stopping
2. **Use the control script** for consistency
3. **Stop properly** with Ctrl+C or the stop command
4. **Verify after starting** that Flask is accessible
5. **Keep terminal open** when running Flask (or use proper service management)

## Quick Reference Card

```
Status:   python flask_control.py status
Stop:     python flask_control.py stop
Start:    python flask_control.py start
Restart:  python flask_control.py restart

Web UI:   http://localhost:5000
API:      http://localhost:5000/api/health
Database: http://localhost:5000/api/database-health

Default port: 5000
Default host: 0.0.0.0 (all interfaces)