"""Prepare an isolated, reviewable currency conversion spread mutation."""

from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[2]
source = root / "data/online-boutique/src/currencyservice/server.js"
case_dir = root / "data/mutations/method_pilot_currency_spread"
case_dir.mkdir(parents=True, exist_ok=True)
original = source.read_text(encoding="utf-8")
needle = "units: euros.units * data[request.to_code],\n        nanos: euros.nanos * data[request.to_code]"
replacement = "units: euros.units * data[request.to_code] * 1.05,\n        nanos: euros.nanos * data[request.to_code] * 1.05"
if original.count(needle) != 1:
    raise SystemExit("Expected conversion expression not found exactly once")
changed = original.replace(needle, replacement)
out = case_dir / "server.js"
out.write_text(changed, encoding="utf-8")
override = case_dir / "compose.override.yml"
override.write_text(
    "services:\n  currencyservice:\n    volumes:\n"
    f"      - {out.as_posix()}:/usr/src/app/server.js:ro\n",
    encoding="utf-8",
)
manifest = {
    "case_id": "pilot_currency_spread_05pct",
    "changed_service": "currencyservice",
    "changed_file": "src/currencyservice/server.js",
    "change_type": "Logic",
    "change_description": "Apply a 5% conversion spread to the destination amount",
    "expected_mechanism": "Convert output changes; frontend and checkout may reflect changed prices",
    "original_sha256": hashlib.sha256(original.encode()).hexdigest(),
    "changed_sha256": hashlib.sha256(changed.encode()).hexdigest(),
}
(case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(override)
