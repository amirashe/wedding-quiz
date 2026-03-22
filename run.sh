#!/bin/bash
set -e

if [ ! -d "venv" ]; then
  echo "❌  לא נמצאת סביבה וירטואלית. הרץ קודם: ./setup.sh"
  exit 1
fi

source venv/bin/activate
python3 app.py
