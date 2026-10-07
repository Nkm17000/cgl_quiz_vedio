from pathlib import Path


def cleanup(paths):
    for path in paths:
        if not path:
            continue
        file = Path(path)
        if file.exists():
            file.unlink()
