#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run install.py first."
    read -p "Press Enter to exit..."
    exit 1
fi
source .venv/bin/activate
echo ""
echo "  AIO Analytics Builder"
echo "  Starting web server..."
echo ""
python3 web-ui/app.py
