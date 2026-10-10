import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "cia_preexperiment_v2"
DATA = Path(os.getenv("MOP_DATA", str(ROOT / "data/runs")))
NAMESPACE = os.getenv("MOP_NAMESPACE", "mop")
CONTEXT = os.getenv("MOP_CONTEXT", "kind-mop")
FRONTEND = os.getenv("MOP_FRONTEND", "http://127.0.0.1:18081")
JAEGER = os.getenv("MOP_JAEGER", "http://127.0.0.1:16687")
