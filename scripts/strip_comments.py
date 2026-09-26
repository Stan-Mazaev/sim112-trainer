"""
Удаляет комментарии из .py и .js.
- Python: через tokenize (не трогает строки, docstrings, защищённые директивы).
- JS: regex-стриппер с защитой кавычек всех типов.
Перед записью делает бэкап в .comment_backup/.
"""
import io
import re
import shutil
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / ".comment_backup"

TARGET_DIRS = [ROOT / "app", ROOT / "scripts", ROOT / "frontend"]

PROTECTED_PREFIXES = (
    "#!", "# -*- coding", "# coding:",
    "# type:", "# noqa", "# pylint:", "# fmt:", "# isort:",
)

SKIP_PARTS = {".venv", "__pycache__", "node_modules", ".git", ".comment_backup"}


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _backup(path: Path) -> None:
    rel = path.relative_to(ROOT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def strip_py(source: str) -> str:
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError) as e:
        print(f"  ! токенайзер упал: {e}")
        return source

    lines = source.splitlines(keepends=True)

    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        line_no = tok.start[0] - 1
        col = tok.start[1]
        line = lines[line_no]

        if any(line.lstrip().startswith(p) for p in PROTECTED_PREFIXES):
            continue

        before = line[:col].rstrip()
        newline = "\n" if line.endswith("\n") else ""
        lines[line_no] = (before + newline) if before else newline

    return "".join(lines)


def strip_js(source: str) -> str:

    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)

    out = []
    for line in source.splitlines(keepends=True):
        idx = 0
        while True:
            idx = line.find("//", idx)
            if idx == -1:
                out.append(line)
                break

            prefix = line[:idx]
            single = prefix.count("'") - prefix.count("\\'")
            double = prefix.count('"') - prefix.count('\\"')
            back = prefix.count("`") - prefix.count("\\`")
            if single % 2 == 0 and double % 2 == 0 and back % 2 == 0:
                before = prefix.rstrip()
                newline = "\n" if line.endswith("\n") else ""
                out.append((before + newline) if before else newline)
                break
            idx += 2
    return "".join(out)


def main() -> None:
    if BACKUP.exists():
        print(f"Бэкап уже есть: {BACKUP}. Удали вручную, если хочешь перезаписать.")
        sys.exit(1)
    BACKUP.mkdir()

    stats = {"py": 0, "js": 0}
    for d in TARGET_DIRS:
        if not d.exists():
            continue
        for ext, func, key in ((".py", strip_py, "py"), (".js", strip_js, "js")):
            for path in d.rglob(f"*{ext}"):
                if _should_skip(path):
                    continue
                src = path.read_text(encoding="utf-8")
                new = func(src)
                if new == src:
                    continue
                _backup(path)
                path.write_text(new, encoding="utf-8")
                stats[key] += 1
                print(f"  {path.relative_to(ROOT)}")

    print(f"\nИтого: py={stats['py']}, js={stats['js']}")
    print(f"Бэкап: {BACKUP}")


if __name__ == "__main__":
    main()