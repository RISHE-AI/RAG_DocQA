#!/usr/bin/env python3
"""
DocQA Studio — Comprehensive Environment & Setup Health Verification
Run: python verify_setup.py
"""

import sys
import os
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent

def print_header(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def check_file(path, label):
    p = BASE_DIR / path
    exists = p.exists()
    status = "✅" if exists else "❌"
    print(f" {status}  {label.ljust(35)} [{path}]")
    return exists

def main():
    print_header("DocQA Studio — System Health & File Verification")
    all_ok = True

    # 1. Project Files
    print("\n📂 Core Architecture Files:")
    all_ok &= check_file("app.py", "Flask Backend & RAG Engine")
    all_ok &= check_file("requirements.txt", "Production Dependencies")
    all_ok &= check_file(".env.example", "Configuration Template")
    all_ok &= check_file("run.bat", "Windows Run Script")
    all_ok &= check_file("run.sh", "Linux/macOS Run Script")
    all_ok &= check_file("README.md", "Project Documentation")

    # 2. Frontend Assets
    print("\n🎨 Modern UI Assets:")
    all_ok &= check_file("templates/index.html", "Main Web Template")
    all_ok &= check_file("static/style.css", "Application Stylesheet")
    all_ok &= check_file("static/script.js", "Client Application Logic")

    # 3. Storage
    print("\n💾 Storage Directories:")
    uploads_dir = BASE_DIR / "uploads"
    if not uploads_dir.exists():
        uploads_dir.mkdir(exist_ok=True)
    all_ok &= check_file("uploads", "Document & Vector Cache")

    # 4. Dependency Imports
    print("\n🐍 Python Library Imports:")
    libraries = [
        ("flask", "Flask Web Framework"),
        ("sentence_transformers", "SentenceTransformers Embedding"),
        ("faiss", "FAISS Vector Indexing"),
        ("fitz", "PyMuPDF Document Parser"),
        ("requests", "HTTP Requests (Groq API)"),
        ("dotenv", "Python Dotenv Config"),
        ("numpy", "NumPy Matrix Operations")
    ]

    for mod_name, label in libraries:
        try:
            __import__(mod_name)
            print(f" ✅  {label.ljust(35)} [OK]")
        except ImportError as e:
            print(f" ❌  {label.ljust(35)} [FAILED: {e}]")
            all_ok = False

    # 5. Groq API Configuration
    print("\n🔑 Groq Cloud Configuration:")
    try:
        from dotenv import load_dotenv
        import requests
        load_dotenv(BASE_DIR / '.env')
        key = os.getenv('GROQ_API_KEY')
        if key and key.startswith('gsk_'):
            print(f" ✅  API Key Found                      [{key[:8]}...{key[-4:]}]")
            # Quick connectivity test
            try:
                res = requests.get(
                    'https://api.groq.com/openai/v1/models',
                    headers={'Authorization': f'Bearer {key}'},
                    timeout=5
                )
                if res.status_code == 200:
                    models = [m['id'] for m in res.json().get('data', []) if not ('whisper' in m['id'] or 'guard' in m['id'])]
                    print(f" ✅  Groq API Online                    [{len(models)} chat models available]")
                else:
                    print(f" ⚠️  Groq API Response: {res.status_code} ({res.text[:80]})")
            except Exception as net_err:
                print(f" ⚠️  Network check skipped: {net_err}")
        else:
            print(" ⚠️  GROQ_API_KEY is not configured in .env (add key before asking questions)")
    except Exception as env_err:
        print(f" ⚠️  Config check warning: {env_err}")

    # Summary
    print_header("Verification Summary")
    if all_ok:
        print("  🎉 All core files and dependencies verified successfully!")
        print("  To launch the studio: python app.py (or run.bat on Windows)")
        print("  Then open: http://localhost:5000\n")
        return 0
    else:
        print("  ⚠️ Some dependencies or files need attention.")
        print("  Run: pip install -r requirements.txt\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
