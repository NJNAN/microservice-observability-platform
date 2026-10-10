"""Prepare historically sourced semantic deltas on the traced runtime.

The catalog cases use exact Git file blobs. Currency/shipping cases replay the
historical business hunks on v0.10.4 so the trace instrumentation remains fixed.
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT / "data/online-boutique"
OUT = ROOT / "data/commits/method_replays"
OUT.mkdir(parents=True, exist_ok=True)


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def parent(commit):
    return git("rev-parse", commit + "^").decode().strip()


def overlay(case_dir, phase, service, source=None, target=None, image=None):
    path = case_dir / f"{phase}.override.yml"
    if source is not None:
        path.write_text(f"services:\n  {service}:\n    volumes:\n      - {source.as_posix()}:{target}:ro\n", encoding="utf-8")
    elif image is not None:
        path.write_text(f"services:\n  {service}:\n    image: {image}\n", encoding="utf-8")
    else:
        path.write_text("services: {}\n", encoding="utf-8")
    return str(path)


def exact_catalog(case_id, commit, description):
    case_dir = OUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    file = "src/productcatalogservice/products.json"
    original = git("show", commit + "^:" + file)
    changed = git("show", commit + ":" + file)
    before = case_dir / "products_original.json"
    after = case_dir / "products_changed.json"
    before.write_bytes(original)
    after.write_bytes(changed)
    return {
        "case_id": case_id, "cohort": "real_commit_replay", "change_type": "Real catalog commit",
        "changed_service": "productcatalogservice", "changed_file": file,
        "commit": git("rev-parse", commit).decode().strip(), "parent": parent(commit),
        "replay_scope": "exact products.json blobs; other historical commit files are not replayed",
        "description": description,
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "changed_sha256": hashlib.sha256(changed).hexdigest(),
        "override_original": overlay(case_dir, "original", "productcatalogservice", before, "/src/products.json"),
        "override_changed": overlay(case_dir, "changed", "productcatalogservice", after, "/src/products.json"),
    }


def replay_currency(case_id, commit, replacements, description):
    case_dir = OUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    source = (REPO / "src/currencyservice/server.js").read_text(encoding="utf-8")
    old = source
    for new, prior in replacements:
        if old.count(new) != 1:
            raise ValueError(f"{case_id}: expected one match of {new[:80]}; got {old.count(new)}")
        old = old.replace(new, prior)
    file = case_dir / "server_original.js"
    file.write_text(old, encoding="utf-8")
    return {
        "case_id": case_id, "cohort": "real_commit_replay", "change_type": "Real currency commit",
        "changed_service": "currencyservice", "changed_file": "src/currencyservice/server.js",
        "commit": git("rev-parse", commit).decode().strip(), "parent": parent(commit),
        "replay_scope": "historical conversion-function hunk ported to traced v0.10.4; not full historical tree",
        "description": description,
        "original_sha256": hashlib.sha256(old.encode()).hexdigest(),
        "changed_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "override_original": overlay(case_dir, "original", "currencyservice", file, "/usr/src/app/server.js"),
        "override_changed": None,
    }


def replay_recommendation():
    case_id = "R06_exclude_seen_9889e4"
    commit = "9889e490"
    case_dir = OUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    source = (REPO / "src/recommendationservice/recommendation_server.py").read_text(encoding="utf-8")
    new = "filtered_products = list(set(product_ids)-set(request.product_ids))"
    prior = "filtered_products = list(product_ids)"
    if source.count(new) != 1:
        raise ValueError("recommendation exclusion hunk not found")
    old = source.replace(new, prior)
    file = case_dir / "recommendation_original.py"
    file.write_text(old, encoding="utf-8")
    return {
        "case_id": case_id, "cohort": "real_commit_replay", "change_type": "Real recommendation commit",
        "changed_service": "recommendationservice", "changed_file": "src/recommendationservice/recommendation_server.py",
        "commit": git("rev-parse", commit).decode().strip(), "parent": parent(commit),
        "replay_scope": "historical exclude-seen hunk ported to traced v0.10.4; not full historical tree",
        "description": "Exclude products already provided in recommendation request",
        "original_sha256": hashlib.sha256(old.encode()).hexdigest(),
        "changed_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "override_original": overlay(case_dir, "original", "recommendationservice", file, "/recommendationservice/recommendation_server.py"),
        "override_changed": None,
    }


def replay_shipping():
    case_id = "R05_flat_shipping_af0515"
    commit = "af0515f7"
    case_dir = OUT / case_id
    source_dir = REPO / "src/shippingservice"
    old_dir = case_dir / "source_original"
    if not old_dir.exists():
        shutil.copytree(source_dir, old_dir)
    main = old_dir / "main.go"
    current_main = (source_dir / "main.go").read_text(encoding="utf-8")
    old_main = current_main.replace(
        "quote := CreateQuoteFromCount(0)",
        "count := 0\n\tfor _, item := range in.Items { count += int(item.Quantity) }\n\tquote := CreateQuoteFromCount(count)",
    )
    if old_main == current_main:
        raise ValueError("shipping GetQuote call was not replaced")
    main.write_text(old_main, encoding="utf-8")
    quote = old_dir / "quote.go"
    current_quote = (source_dir / "quote.go").read_text(encoding="utf-8")
    old_quote = current_quote.replace(
        "return CreateQuoteFromFloat(8.99)",
        "if count == 0 { return CreateQuoteFromFloat(0) }\n\tcount64 := float64(count)\n\tp := 1 + count64 * 0.2\n\treturn CreateQuoteFromFloat(count64 + math.Pow(3, p))",
    )
    if old_quote == current_quote:
        raise ValueError("shipping quote formula was not replaced")
    quote.write_text(old_quote, encoding="utf-8")
    image = "cia-online-boutique-shippingservice:real-af051-original"
    return {
        "case_id": case_id, "cohort": "real_commit_replay", "change_type": "Real shipping commit",
        "changed_service": "shippingservice", "changed_file": "src/shippingservice/main.go + quote.go",
        "commit": git("rev-parse", commit).decode().strip(), "parent": parent(commit),
        "replay_scope": "historical item-count quote formula ported to traced v0.10.4; not full historical tree",
        "description": "Replace item-count shipping formula with a flat $8.99 fee",
        "original_sha256": hashlib.sha256((old_main + old_quote).encode()).hexdigest(),
        "changed_sha256": hashlib.sha256((current_main + current_quote).encode()).hexdigest(),
        "build_context": str(old_dir), "original_image": image,
        "override_original": overlay(case_dir, "original", "shippingservice", image=image),
        "override_changed": None,
    }


def main():
    cases = [
        exact_catalog("R01_catalog_refresh_d2c729", "d2c729d1", "Replace vintage catalog with Cymbal product list"),
        exact_catalog("R02_camera_name_9b4e81", "9b4e81ef", "Rename Vintage Camera Lens to Antique Camera"),
        replay_currency("R03_nanos_rounding_076819", "076819d0", [
            ("euros.nanos = Math.round(euros.nanos);", "// old revision rounded only after destination conversion"),
            ("result.units = Math.floor(result.units);\n      result.nanos = Math.floor(result.nanos);", "result.nanos = Math.round(result.nanos);"),
        ], "Fix nano-unit overflow in conversion rounding"),
        replay_currency("R04_carry_math_97a36a", "97a36a63", [
            ("amount.units = Math.floor(amount.units) + Math.floor(amount.nanos / fractionSize);", "amount.units = Math.floor(amount.units + amount.nanos / fractionSize);"),
        ], "Fix double-counting of fractional units in carry arithmetic"),
        replay_shipping(),
        replay_recommendation(),
    ]
    for case in cases:
        case_dir = OUT / case["case_id"]
        (case_dir / "manifest.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    (OUT / "cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(json.dumps({"prepared": len(cases), "commits": [case["commit"] for case in cases]}, indent=2))


if __name__ == "__main__":
    main()
