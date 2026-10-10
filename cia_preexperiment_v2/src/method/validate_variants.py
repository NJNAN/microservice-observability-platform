"""Syntax and manifest checks for generated controlled variants."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
cases = json.loads((ROOT / "data/mutations/method_controlled/cases.json").read_text(encoding="utf-8"))
errors = []
for case in cases:
    case_dir = ROOT / "data/mutations/method_controlled" / case["case_id"]
    for path in case_dir.iterdir():
        if path.name == "manifest.json":
            continue
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        elif path.suffix == ".js":
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            if result.returncode:
                errors.append((case["case_id"], result.stderr))
print(json.dumps({"cases": len(cases), "syntax_errors": errors}, indent=2))
if errors:
    raise SystemExit(1)
