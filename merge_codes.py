# -*- coding: utf-8 -*-
"""جمع ملفات المصدر النصية في تقرير واحد، مع استثناء المخرجات والبيئات الافتراضية."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT = BASE_DIR / "جميع_الأكواد.txt"
EXTENSIONS = {".py", ".js", ".html", ".css", ".txt", ".json", ".sql"}
EXCLUDED = {".venv", "venv", "__pycache__", ".git", "build", "dist"}

with OUTPUT.open("w", encoding="utf-8") as out:
    for path in sorted(BASE_DIR.rglob("*")):
        if not path.is_file() or path == OUTPUT or path.suffix.lower() not in EXTENSIONS:
            continue
        if any(part in EXCLUDED for part in path.parts):
            continue
        out.write("=" * 70 + "\n")
        out.write(f"اسم الملف: {path.name}\nالمسار: {path}\n")
        out.write("=" * 70 + "\n\n")
        try: out.write(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc: out.write(f"تعذر قراءة الملف: {exc}\n")
        out.write("\n\n")
print(f"تم إنشاء التقرير: {OUTPUT}")
