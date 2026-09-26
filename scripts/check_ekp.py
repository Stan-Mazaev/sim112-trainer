"""Быстрая проверка classifier.json — выводит первые N типов и статистику."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSIFIER = ROOT / "app" / "sim112" / "ekp" / "classifier.json"

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 10


def main():
    with CLASSIFIER.open(encoding="utf-8") as f:
        data = json.load(f)

    print(f"Всего типов: {data['total_types']}")
    print(f"Групп: {len(data['groups'])}")
    print()
    print(f"--- Первые {LIMIT} типов ---")
    for t in data["types"][:LIMIT]:
        svc = ", ".join(t["services"]) if t["services"] else "—"
        signs = " / ".join(
            x for x in (t["sign_l1"], t["sign_l2"], t["sign_l3"]) if x
        ) or "—"
        print(f"  {t['id']:<10} | {t['group_name']}")
        print(f"     тип:   {t['final_type']}")
        print(f"     знаки: {signs}")
        print(f"     службы: {svc}")
        print()


if __name__ == "__main__":
    main()