"""Isi .env nota.ekstrak dari kunci yang sudah ada di mesin ini.

Skrip ini menulis ke .env (sudah masuk .gitignore). Nilainya tidak pernah
dicetak. Jalankan sekali setelah membuat berkas .env kosong:

    python scripts/seed_env.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".env"


def main():
    API_KEY = os.environ.get("RIVER_API_KEY", "")
    if not API_KEY:
        return "RIVER_API_KEY tidak ada di environment"

    lines = []
    if TARGET.exists():
        for line in TARGET.read_text().splitlines():
            name = line.split("=", 1)[0].strip()
            if name in ("", "RIVER_API_KEY"):
                continue
            lines.append(line)
    lines.insert(0, f"RIVER_API_KEY={API_KEY}")
    TARGET.write_text("\n".join(lines) + "\n")
    TARGET.chmod(0o600)
    return f"ditulis ke {TARGET} (mode 600)"


if __name__ == "__main__":
    print(main())
    sys.exit(0)
