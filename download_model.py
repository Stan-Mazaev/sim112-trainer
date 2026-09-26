"""Скачивание Vosk-модели через httpx с retry и прогрессом."""

from pathlib import Path
import httpx


URLS = [
    "https://huggingface.co/alphacep/vosk-model-small-ru/resolve/main/vosk-model-small-ru-0.22.zip?download=true",
    "https://hf-mirror.com/alphacep/vosk-model-small-ru/resolve/main/vosk-model-small-ru-0.22.zip?download=true",
    "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
]

OUT = Path("data/vosk/model-ru.zip")


def try_download(url: str) -> bool:
    print(f"\n→ Пробую: {url}")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with OUT.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done * 100 // total
                        print(f"\r  {pct}% ({done}/{total})", end="", flush=True)
            print()
        size = OUT.stat().st_size
        if size > 10_000_000:
            print(f"  ✅ Скачано {size / 1024 / 1024:.1f} МБ")
            return True
        print(f"  ❌ Файл слишком мал ({size} байт), вероятно ошибка")
        OUT.unlink(missing_ok=True)
        return False
    except Exception as exc:
        print(f"  ❌ Ошибка: {exc}")
        OUT.unlink(missing_ok=True)
        return False


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for url in URLS:
        if try_download(url):
            print("\nГотово.")
            return
    print("\nВсе источники недоступны. Смотри инструкцию про ручную загрузку.")


if __name__ == "__main__":
    main()