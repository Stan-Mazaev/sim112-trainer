"""Список всех зарегистрированных роутов — для отладки."""

from app.main import app


def main():
    rows = []
    for r in app.routes:
        if not hasattr(r, "path") or not hasattr(r, "methods"):
            continue
        methods = sorted(m for m in r.methods if m != "HEAD")
        for m in methods:
            rows.append((r.path, m))

    rows.sort()
    print(f"Всего: {len(rows)}\n")
    for path, method in rows:
        marker = ""
        if "simulation" in path or "instructor" in path:
            marker = "  ← важно"
        print(f"{method:8} {path}{marker}")


if __name__ == "__main__":
    main()