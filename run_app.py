# -*- coding: utf-8 -*-
"""مشغل Streamlit من مجلد المشروع نفسه."""
from __future__ import annotations
import sys
from pathlib import Path
from streamlit.web import cli

BASE_DIR = Path(__file__).resolve().parent
APP_PATH = BASE_DIR / "app.py"
if __name__ == "__main__":
    if not APP_PATH.is_file():
        raise SystemExit(f"لم يتم العثور على ملف التطبيق: {APP_PATH}")
    sys.path.insert(0, str(BASE_DIR))
    sys.argv = ["streamlit", "run", str(APP_PATH), "--global.developmentMode=false", "--server.headless=true"]
    cli.main()
