#!/bin/bash

echo ""
echo "==================================================="
echo "  DocQA Studio - Enterprise RAG Platform"
echo "==================================================="
echo ""

# 1. Verify Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    echo "Please install Python 3.10+ from https://www.python.org/"
    exit 1
fi

# 2. Ensure virtual environment exists
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment (venv)..."
    python3 -m venv venv
fi

# 3. Activate virtual environment
echo "[*] Activating virtual environment..."
source venv/bin/activate

# 4. Check dependencies
echo "[*] Checking dependencies..."
pip install -r requirements.txt -q

# 5. Check configuration
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "[*] Initializing .env from .env.example..."
    cp .env.example .env
    echo "[NOTICE] Please configure GROQ_API_KEY in .env"
fi

# 6. Launch Application
echo ""
echo "[*] Starting DocQA Studio server..."
echo "==================================================="
echo "  URL: http://localhost:5000"
echo "  Press Ctrl+C to terminate"
echo "==================================================="
echo ""

python app.py
