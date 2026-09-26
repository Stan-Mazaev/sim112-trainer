"""
Парсер классификатора происшествий ЕКП (версия 046-24).

Структура Excel:
  - Заголовок группы: cols A-D пустые, E = номер группы (1..30), F = название.
  - Строка типа: A-D = номера (Г, п1, п2, п3), E = формула-номер, F = длинное описание,
                 G,H,I = признаки 1-3, J = доп. признаки, K = итоговый тип,
                 L = ЕКП-35, M = главная служба.
"""

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
OUT_DIR = ROOT / "app" / "sim112" / "ekp"
OUT_FILE = OUT_DIR / "classifier.json"


SERVICE_MAP = {
    "mchs": "fire",
    "fire": "fire",
    "police": "police",
    "ambulance": "ambulance",
    "gas": "gas",
    "mosgaz": "gas",
    "metro": "metro",
    "moslift": "lift",
    "mzd": "rail",
    "mosvodocanal": "water",
    "moek": "heat",
    "moesk": "power",
    "oek": "power",
    "gkh": "gkh",
    "autoroads": "roads",
    "gormost": "roads",
    "mosgortrans": "transport",
    "mosvodostok": "drainage",
    "moscowcollector": "collector",
    "dep.tszn": "social",
    "deptszn": "social",
    "msppn": "psychology",
    "zodd": "traffic",
    "zemp": "medical_center",
    "msp": "medical_small",
}


def find_excel() -> Path:
    for pattern in ("*Классификатор*.xlsx", "*классификатор*.xlsx"):
        matches = list(DOCS_DIR.glob(pattern))
        if matches:
            return matches[0]
    raise FileNotFoundError(
        f"Не нашёл Excel классификатора в {DOCS_DIR}. "
        f"Положи файл вида 'Классификатор_происшествий_*.xlsx' в docs/."
    )


def clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def parse_int(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (ValueError, OverflowError):
            return None
    if isinstance(value, str):
        if value.startswith("="):
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
    return None


def map_services(raw) -> list[str]:
    raw = clean(raw)
    if not raw:
        return []
    parts = re.split(r"[,;/]", raw)
    result = []
    for p in parts:
        p = p.strip().lower()
        if not p:
            continue
        words = p.split()
        key = words[0] if words else p
        mapped = SERVICE_MAP.get(key, key)
        if mapped not in result:
            result.append(mapped)
    return result


def detect_group_header(row, cols):
    """Возвращает (group_id, group_name), если строка — заголовок группы."""
    for i in range(4):
        if parse_int(row[cols[i]]) is not None:
            return None
    e_int = parse_int(row[cols[4]])
    if e_int is None or not (1 <= e_int <= 30):
        return None
    f_str = clean(row[cols[5]])
    if not f_str or len(f_str) > 200:
        return None
    if f_str.lower().startswith(("учет", "группа происшествий", "блок,")):
        return None
    return (e_int, f_str)


def main():
    excel = find_excel()
    print(f"[parse_ekp] Читаю: {excel.name}")

    df = pd.read_excel(excel, sheet_name=0, header=0, dtype=object)
    print(f"[parse_ekp] Всего строк: {len(df)}")

    cols = df.columns.tolist()
    print(f"[parse_ekp] Колонок: {len(cols)}")
    if len(cols) < 13:
        raise ValueError(f"Ожидалось минимум 13 колонок, найдено {len(cols)}")

    types: list[dict] = []
    groups: dict[int, dict] = {}
    seen_ids: set[str] = set()

    for idx, row in df.iterrows():

        gh = detect_group_header(row, cols)
        if gh:
            gid, gname = gh
            if gid not in groups:
                groups[gid] = {"id": gid, "name": gname, "types_count": 0}
            continue


        a_int = parse_int(row[cols[0]])
        b_int = parse_int(row[cols[1]])
        c_int = parse_int(row[cols[2]])
        d_int = parse_int(row[cols[3]])
        k_val = clean(row[cols[10]])

        if a_int is None or k_val is None:
            continue
        if any(x is None for x in (b_int, c_int, d_int)):
            continue

        item_id = f"{a_int}.{b_int}.{c_int}.{d_int}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        item = {
            "id": item_id,
            "group_id": a_int,
            "group_name": groups.get(a_int, {}).get("name"),
            "sign_l1": clean(row[cols[6]]),
            "sign_l2": clean(row[cols[7]]),
            "sign_l3": clean(row[cols[8]]),
            "additional_signs": clean(row[cols[9]]),
            "final_type": k_val,
            "ekp35_type": clean(row[cols[11]]),
            "main_service": clean(row[cols[12]]),
            "services": map_services(row[cols[12]]),
        }
        types.append(item)

        if a_int in groups:
            groups[a_int]["types_count"] += 1

    for item in types:
        if item["group_name"] is None and item["group_id"] in groups:
            item["group_name"] = groups[item["group_id"]]["name"]

    print(f"[parse_ekp] Распознано типов: {len(types)}")
    print(f"[parse_ekp] Групп: {len(groups)}")
    for g in sorted(groups.values(), key=lambda x: x["id"]):
        print(f"  {g['id']}: {g['name']} ({g['types_count']} типов)")

    output = {
        "version": "046-24",
        "source_file": excel.name,
        "total_types": len(types),
        "groups": sorted(groups.values(), key=lambda x: x["id"]),
        "types": types,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[parse_ekp] Записано в {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()