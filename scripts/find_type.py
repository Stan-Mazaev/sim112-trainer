"""Поиск типа происшествия в classifier.json по ключевому слову.

Использование:
    python scripts/find_type.py мусор
    python scripts/find_type.py кровотечение
    python scripts/find_type.py зажаты
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSIFIER = ROOT / "app" / "sim112" / "ekp" / "classifier.json"


def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/find_type.py <ключевое_слово>")
        sys.exit(1)

    query = sys.argv[1].lower().strip()

    with CLASSIFIER.open(encoding="utf-8") as f:
        data = json.load(f)

    matches = []
    for t in data["types"]:
        haystack = " ".join(filter(None, [
            t["final_type"],
            t["sign_l1"], t["sign_l2"], t["sign_l3"],
            t["additional_signs"],
            t["group_name"],
        ])).lower()

        if query in haystack:
            matches.append(t)

    if not matches:
        print(f"Ничего не найдено по '{query}'")
        return

    print(f"Найдено: {len(matches)}")
    print()
    for t in matches[:30]:
        svc = ", ".join(t["services"]) if t["services"] else "—"
        signs = " / ".join(
            x for x in (t["sign_l1"], t["sign_l2"], t["sign_l3"]) if x
        ) or "—"
        print(f"  {t['id']:<10} | {t['final_type']}")
        print(f"     группа: {t['group_name']}")
        print(f"     знаки:  {signs}")
        print(f"     службы: {svc}")
        print()

    if len(matches) > 30:
        print(f"... и ещё {len(matches) - 30}")


if __name__ == "__main__":
    main()