import json
import os
from pathlib import Path

from .settings import DATA


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def experiments():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(DATA.glob("*/result.json"), reverse=True)]
