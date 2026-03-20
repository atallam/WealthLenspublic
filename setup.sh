#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║  WealthLens OSS — Local Development Setup                   ║
# ║  Usage: chmod +x setup.sh && ./setup.sh                    ║
# ╚══════════════════════════════════════════════════════════════╝

set -e
echo "🔐 WealthLens OSS — Setting up development environment..."

# --- Generate .env if missing ---
if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    # Generate random keys
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
    SALT=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s|CHANGE-ME-to-a-64-char-random-string|$SECRET|g" .env
    sed -i "s|CHANGE-ME-another-random-string-for-key-derivation|$SALT|g" .env
    echo "   ✅ Generated random SECRET_KEY and ENCRYPTION_MASTER_SALT"
fi

# --- Python backend ---
echo "🐍 Setting up Python backend..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt --quiet
echo "   ✅ Python dependencies installed"

# --- React frontend ---
echo "⚛️  Setting up React frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
echo "   ✅ Frontend dependencies installed"
cd ..

echo ""
echo "════════════════════════════════════════════════════"
echo " ✅ Setup complete! To start development:"
echo ""
echo "   Terminal 1 (backend):  source venv/bin/activate && uvicorn app.main:app --reload"
echo "   Terminal 2 (frontend): cd frontend && npm run dev"
echo ""
echo "   Then open: http://localhost:5173"
echo ""
echo "   For Docker deployment: docker compose up -d"
echo "════════════════════════════════════════════════════"
