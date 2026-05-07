#!/usr/bin/env python3
"""Start Flask app without debug mode to avoid reloading"""

import subprocess
import sys
import os
import argparse

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Start Flask application for API Test Command Center')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode (not recommended for production)')
    return parser.parse_args()

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = ['flask', 'pyodbc', 'openpyxl']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    return missing_packages

def main():
    """Main function to start Flask app"""
    args = parse_arguments()
    
    # Change to the script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("=" * 60)
    print("API Test Command Center - Flask Application")
    print("=" * 60)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Debug mode: {args.debug}")
    print("-" * 60)
    
    # Check dependencies
    print("Checking dependencies...")
    missing = check_dependencies()
    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        print("Installing from requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            print("Please install manually: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("All dependencies are installed.")
    
    # Start Flask app
    print("-" * 60)
    print(f"Starting Flask server on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        # Import and run the app directly
        import app
        # Run with specified parameters
        app.app.run(
            debug=args.debug,
            host=args.host,
            port=args.port,
            use_reloader=args.debug  # Only use reloader in debug mode
        )
    except KeyboardInterrupt:
        print("\nFlask app stopped by user")
    except Exception as e:
        print(f"Error starting Flask app: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if port {args.port} is already in use")
        print("2. Verify all dependencies are installed")
        print("3. Check database connection if using database features")
        sys.exit(1)

if __name__ == "__main__":
    main()