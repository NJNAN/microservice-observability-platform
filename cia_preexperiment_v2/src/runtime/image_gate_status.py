"""Record which pinned/declared Compose images are locally available."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.compose.read_text(encoding="utf-8"))
    rows = []
    for service, specification in config["services"].items():
        image = specification["image"]
        proc = subprocess.run(["docker", "image", "inspect", image, "--format", "{{json .}}"],
                              text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=20)
        if proc.returncode == 0:
            details = json.loads(proc.stdout)
            rows.append({"service": service, "image": image, "available": True,
                         "image_id": details.get("Id"), "repo_digests": details.get("RepoDigests", [])})
        else:
            rows.append({"service": service, "image": image, "available": False,
                         "error": proc.stderr.strip()[:500]})
    outcome = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "compose": str(args.compose), "services": rows,
               "available_count": sum(row["available"] for row in rows), "required_count": len(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"available": outcome["available_count"], "required": outcome["required_count"],
                      "missing": [row["service"] for row in rows if not row["available"]]}, ensure_ascii=False))
