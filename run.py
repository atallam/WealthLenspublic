"""
WealthLens OSS — Replit/Simple Runner
Builds frontend (if needed), starts the FastAPI server.
"""

import subprocess
import os
import sys


def build_frontend():
    """Build React frontend if dist doesn't exist."""
    dist = os.path.join("frontend", "dist")
    if not os.path.isdir(dist):
        print("⚛️  Building frontend...")
        subprocess.run(["npm", "install"], cwd="frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd="frontend", check=True)
        print("   ✅ Frontend built")
    else:
        print("   ✅ Frontend already built")


def ensure_secrets():
    """Generate secrets if not set."""
    import secrets
    if not os.environ.get("SECRET_KEY"):
        os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
        print("   🔑 Generated SECRET_KEY")
    if not os.environ.get("ENCRYPTION_MASTER_SALT"):
        os.environ["ENCRYPTION_MASTER_SALT"] = secrets.token_urlsafe(32)
        print("   🔑 Generated ENCRYPTION_MASTER_SALT")


if __name__ == "__main__":
    print("🔐 WealthLens OSS — Starting...")
    ensure_secrets()

    # Install Python deps
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"], check=True)

    build_frontend()

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    print(f"\n🚀 Server starting on http://{host}:{port}")
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
