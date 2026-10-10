"""Create a reviewable public source tree without nested Git stores/build caches.

Original research evidence is never removed. Existing destinations are rejected.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("destination", type=Path)
    destination = p.parse_args().destination.resolve()
    if destination.exists():
        p.error("Destination must not already exist")
    if not destination.is_relative_to(ROOT / "dist"):
        p.error("Use a new directory under dist/")
    paths = ["README.md", "LICENSE", "NOTICE", "Makefile", "PROJECT_V1_AUDIT.md", "PROJECT_V1_COMPLETION.md",
             ".gitignore", ".gitattributes", ".dockerignore", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
             "docker-compose.yml", "assets", "obsplatform", "scripts", "tests", "build", "configs", "dashboards", "docs", "k8s", ".github",
             "data/README.md", "data/validation", "research/README.md",
             "cia_preexperiment_v2/data/online-boutique/src", "cia_preexperiment_v2/data/online-boutique/LICENSE",
             "cia_preexperiment_v2/data/online-boutique/release/kubernetes-manifests.yaml",
             "cia_preexperiment_v2/src/runtime", "cia_preexperiment_v2/src/method",
             "cia_preexperiment_v2/configs", "cia_preexperiment_v2/data/mutations/method_controlled",
             "cia_preexperiment_v2/data/commits/method_replays", "cia_preexperiment_v2/results/raw/online_boutique_trace_gate",
             "cia_preexperiment_v2/results/tables/method_experiment"]
    destination.mkdir(parents=True)
    for relative in paths:
        source = ROOT / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", "*.jar", "bin", "obj"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    manifest = {str(f.relative_to(destination)).replace("\\", "/"): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in destination.rglob("*") if f.is_file()}
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print(f"Exported {len(manifest)} files to {destination}; original workspace unchanged")


if __name__ == "__main__":
    main()
