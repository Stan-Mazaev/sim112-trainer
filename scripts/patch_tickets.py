"""
Точечные правки classification_id/services в ticket_*.json.
Пересобирает только нужные поля, остальное не трогает.
"""
import json
from pathlib import Path

TICKETS_DIR = Path(__file__).resolve().parents[1] / "app" / "sim112" / "scenarios" / "tickets"

PATCHES: dict[str, dict[str, dict]] = {
    "ticket_23.json": {
        "ticket_23_case_02": {
            "expected": {
                "classification_id": "22.23.0.0",
                "classification_name": "Кровотечение",
            },
        },
    },
    "ticket_25.json": {
        "ticket_25_case_02": {
            "expected": {
                "classification_id": "2.1.1.0",
                "classification_name": "ДТП без пострадавших - легковой",
            },
        },
    },
    "ticket_27.json": {
        "ticket_27_case_02": {
            "expected": {
                "classification_id": "2.1.10.0",
                "classification_name": "ДТП без пострадавших - тоннель путепровод",
            },
        },
        "ticket_27_case_03": {
            "expected": {
                "classification_id": "14.3.1.0",
                "classification_name": "Частная проблема коммунального характера",
                "services": ["gkh"],
                "services_ekp": ["gkh"],
            },
        },
    },
}


def patch() -> None:
    for filename, scenario_patches in PATCHES.items():
        path = TICKETS_DIR / filename
        if not path.exists():
            print(f"SKIP: {path} не найден")
            continue

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        changes: list[str] = []
        for sc in data.get("scenarios", []):
            sid = sc.get("id")
            if sid not in scenario_patches:
                continue
            for field, new_val in scenario_patches[sid].get("expected", {}).items():
                old_val = sc.get("expected", {}).get(field)
                if old_val == new_val:
                    continue
                sc["expected"][field] = new_val
                changes.append(f"  {sid}.expected.{field}: {old_val!r} → {new_val!r}")

        if changes:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"PATCHED {filename}:")
            for c in changes:
                print(c)
        else:
            print(f"NOCHANGE {filename}")


if __name__ == "__main__":
    patch()