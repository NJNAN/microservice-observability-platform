"""One orchestration implementation for Linux, Windows and CI."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def kind():
    return shutil.which("kind") or str(ROOT / "tools/kind.exe")


def load_image(image):
    # Docker Desktop's containerd image store may retain an index without all
    # architectures. Export only the platform supported by this V1 lab.
    path = ROOT / ".runtime" / (hashlib.sha256(image.encode()).hexdigest()[:12] + ".tar")
    path.parent.mkdir(exist_ok=True)
    try:
        run("docker", "image", "save", "--platform=linux/amd64", "-o", path, image)
        run(kind(), "load", "image-archive", path, "--name", "mop")
    finally:
        if path.exists():
            path.unlink()


def build(reuse=False):
    import yaml
    images = yaml.safe_load((ROOT / "configs/images.yaml").read_text())
    for service, image in images.items():
        if not image.startswith("mop-"):
            if reuse and subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0:
                continue
            run("docker", "pull", image)
            continue
        if reuse and service in ("shippingservice", "checkoutservice", "cartservice"):
            run("docker", "tag", f"cia-online-boutique-{service}:trace-gate", image)
        elif reuse and service in ("currencyservice", "paymentservice"):
            entry = "server.js" if service == "currencyservice" else "index.js"
            path = ROOT / ".runtime" / f"{service}.Dockerfile"
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"FROM cia-online-boutique-{service}:trace-gate\nCOPY cia_preexperiment_v2/data/online-boutique/src/{service}/{entry} /usr/src/app/{entry}\n")
            run("docker", "build", "-t", image, "-f", path, ".")
        elif service in ("shippingservice", "checkoutservice"):
            run("docker", "build", "-t", image, ROOT / f"cia_preexperiment_v2/data/online-boutique/src/{service}")
        else:
            run("docker", "build", "-t", image, "-f", f"build/{service}.Dockerfile", ".")
    replay_image = "cia-online-boutique-shippingservice:real-af051-original"
    if not reuse or subprocess.run(["docker", "image", "inspect", replay_image], capture_output=True).returncode:
        run("docker", "build", "-t", replay_image,
            "cia_preexperiment_v2/data/commits/method_replays/R05_flat_shipping_af0515/source_original")
    run("docker", "build", "-t", "mop-platform:v1", "-f", "build/platform.Dockerfile", ".")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["setup", "generate", "build", "up", "status", "demo", "mutation", "test", "down", "ports"])
    p.add_argument("--reuse-local-tracing-images", action="store_true", help="Local development only; CI rebuilds source")
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--case", default="C01_catalog_price")
    a = p.parse_args()
    if a.action == "setup":
        run(sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt")
    elif a.action == "generate":
        run(sys.executable, "scripts/generate.py")
    elif a.action == "build":
        build(a.reuse_local_tracing_images)
    elif a.action == "up":
        import yaml
        run(sys.executable, "scripts/generate.py")
        if not a.skip_build:
            build(a.reuse_local_tracing_images)
        clusters = subprocess.check_output([kind(), "get", "clusters"], text=True).splitlines()
        if "mop" not in clusters:
            run(kind(), "create", "cluster", "--name", "mop", "--image", "kindest/node:v1.32.2", "--wait", "120s")
        images = yaml.safe_load((ROOT / "configs/images.yaml").read_text())
        stack = yaml.safe_load_all((ROOT / "k8s/observability/stack.yaml").read_text())
        observability = [d["spec"]["template"]["spec"]["containers"][0]["image"] for d in stack if d["kind"] == "Deployment"]
        for image in observability:
            if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
                run("docker", "pull", image)
        for image in [*images.values(), "mop-platform:v1", "cia-online-boutique-shippingservice:real-af051-original", *observability]:
            load_image(image)
        run("kubectl", "--context", "kind-mop", "apply", "-k", "k8s")
        run("kubectl", "--context", "kind-mop", "-n", "mop", "wait", "--for=condition=Available", "deployment", "--all", "--timeout=600s")
    elif a.action == "status":
        run("kubectl", "--context", "kind-mop", "-n", "mop", "get", "pods,svc")
    elif a.action in ("demo", "mutation"):
        command = ["demo"] if a.action == "demo" else ["mutation", "run", a.case]
        run("kubectl", "--context", "kind-mop", "-n", "mop", "exec", "deployment/platform", "--", "python", "-m", "obsplatform.cli", *command)
    elif a.action == "test":
        run(sys.executable, "-m", "ruff", "check", "obsplatform", "scripts", "tests")
        run(sys.executable, "-m", "pytest", "-q")
        run(sys.executable, "scripts/validate.py")
    elif a.action == "down":
        run(kind(), "delete", "cluster", "--name", "mop")
    elif a.action == "ports":
        children = []
        try:
            for service, mapping in {"frontend": "18081:80", "jaeger": "16687:16686", "prometheus": "9090:9090", "grafana": "3000:3000", "platform": "8000:8000"}.items():
                children.append(subprocess.Popen(["kubectl", "--context", "kind-mop", "-n", "mop", "port-forward", "service/" + service, mapping, "--address", "127.0.0.1"]))
            print(json.dumps({"frontend": 18081, "jaeger": 16687, "prometheus": 9090, "grafana": 3000, "api": 8000}))
            while all(c.poll() is None for c in children):
                import time
                time.sleep(1)
            raise RuntimeError("A port-forward exited; check local port conflicts")
        except KeyboardInterrupt:
            pass
        finally:
            for child in children:
                child.terminate()


if __name__ == "__main__":
    main()
