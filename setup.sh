#!/bin/bash
set -e

echo ""
echo "════════════════════════════════════════"
echo "  🎊  הכנת אפליקציית החתונה"
echo "════════════════════════════════════════"

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌  לא נמצא python3. אנא התקן Python 3.10+"
  exit 1
fi

echo "✅  Python נמצא: $(python3 --version)"

# Create venv
if [ ! -d "venv" ]; then
  echo "📦  יוצר סביבה וירטואלית..."
  python3 -m venv venv
fi

# Activate & install
source venv/bin/activate
echo "📦  מתקין חבילות Python..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅  חבילות הותקנו"

# Install ngrok (optional)
if ! command -v ngrok &>/dev/null && [ ! -f "venv/bin/ngrok" ]; then
  echo ""
  echo "────────────────────────────────────────"
  echo "  📡  מתקין ngrok (לכתובת ציבורית)..."
  echo "────────────────────────────────────────"
  ARCH=$(uname -m)
  if [ "$ARCH" = "x86_64" ]; then
    NGROK_ZIP="ngrok-v3-stable-linux-amd64.zip"
  elif [ "$ARCH" = "aarch64" ]; then
    NGROK_ZIP="ngrok-v3-stable-linux-arm64.zip"
  else
    echo "⚠️  ארכיטקטורה לא מזוהה. הורד ngrok ידנית מ: https://ngrok.com/download"
    NGROK_ZIP=""
  fi

  if [ -n "$NGROK_ZIP" ]; then
    curl -sL "https://bin.equinox.io/c/bNyj1mQVY4c/${NGROK_ZIP}" -o /tmp/ngrok.zip
    unzip -q /tmp/ngrok.zip -d venv/bin/
    rm /tmp/ngrok.zip
    chmod +x venv/bin/ngrok
    echo "✅  ngrok הותקן"
  fi
fi

echo ""
echo "════════════════════════════════════════"
echo "  ✅  הכל מוכן!"
echo "  הרץ:  ./run.sh"
echo "════════════════════════════════════════"
echo ""
