#!/bin/bash
# ─────────────────────────────────────────────
#  StationScheduler — installer
#  Double-click this file to install
# ─────────────────────────────────────────────

REPO_URL="https://github.com/josemartin727272-arch/StationScheduler.git"
INSTALL_DIR="$HOME/StationScheduler"

echo "╔══════════════════════════════════════╗"
echo "║   StationScheduler — התקנה           ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── Check Python ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ Python3 לא מותקן."
    echo "   הורד מ: https://www.python.org/downloads/"
    read -p "לחץ Enter לסיום..."
    exit 1
fi
echo "✅ Python3 נמצא: $(python3 --version)"

# ── Clone or update repo ──────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo ""
    echo "📁 תיקייה קיימת — מעדכן..."
    cd "$INSTALL_DIR" && git pull
else
    echo ""
    echo "📥 מוריד את האפליקציה..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

if [ $? -ne 0 ]; then
    echo "❌ שגיאה בהורדה. בדוק חיבור לאינטרנט."
    read -p "לחץ Enter לסיום..."
    exit 1
fi

cd "$INSTALL_DIR"

# ── Install Python dependencies ───────────────
echo ""
echo "📦 מתקין תלויות Python..."
python3 -m pip install -r requirements.txt --quiet

if [ $? -ne 0 ]; then
    echo "⚠️  שגיאה בהתקנת תלויות — מנסה שוב..."
    python3 -m pip install streamlit openpyxl --quiet
fi
echo "✅ תלויות הותקנו"

# ── Create launcher .app ──────────────────────
echo ""
echo "🖥  יוצר קיצור דרך על שולחן העבודה..."

LAUNCH_SCRIPT=$(cat <<APPLESCRIPT
on run
    set appDir to "$INSTALL_DIR"
    do shell script "pkill -f 'streamlit run app.py' 2>/dev/null; true"
    delay 1
    do shell script "cd " & quoted form of appDir & " && python3 -m streamlit run app.py --server.headless true > /tmp/stationscheduler.log 2>&1 &"
    delay 4
    open location "http://localhost:8501"
end run
APPLESCRIPT
)

echo "$LAUNCH_SCRIPT" > /tmp/launcher.scpt
osacompile -o "$HOME/Desktop/📅 StationScheduler.app" /tmp/launcher.scpt
xattr -cr "$HOME/Desktop/📅 StationScheduler.app"

# ── Create update script ──────────────────────
cat > "$HOME/Desktop/🔄 עדכון StationScheduler.command" << 'UPDATESCRIPT'
#!/bin/bash
INSTALL_DIR="$HOME/StationScheduler"
echo "🔄 מעדכן StationScheduler..."
cd "$INSTALL_DIR"
git pull
echo ""
echo "📦 מעדכן תלויות..."
python3 -m pip install -r requirements.txt --quiet
echo ""
echo "✅ עדכון הושלם! סגור חלון זה ופתח מחדש את האפליקציה."
read -p "לחץ Enter לסיום..."
UPDATESCRIPT

chmod +x "$HOME/Desktop/🔄 עדכון StationScheduler.command"

# ── Done ──────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ✅  ההתקנה הושלמה בהצלחה!         ║"
echo "║                                      ║"
echo "║   על שולחן העבודה:                   ║"
echo "║   📅 StationScheduler  — להפעלה      ║"
echo "║   🔄 עדכון StationScheduler — לעדכון ║"
echo "╚══════════════════════════════════════╝"
echo ""
read -p "לחץ Enter לסיום..."
