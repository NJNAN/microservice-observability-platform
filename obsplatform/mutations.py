"""Serialized Kubernetes experiments with a durable baseline restoration journal."""
import copy
import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager

import yaml

from . import settings
from .experiments import collect
from .storage import save


def catalog():
    path = settings.ROOT / "configs/mutations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def case_by_id(case_id):
    return next((c for c in catalog() if c["case_id"] == case_id), None)


def kubectl(*args, payload=None):
    cmd = ["kubectl"]
    if not os.getenv("KUBERNETES_SERVICE_HOST"):
        cmd += ["--context", settings.CONTEXT]
    cmd += ["-n", settings.NAMESPACE, *args]
    result = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout


@contextmanager
def exclusive():
    settings.DATA.mkdir(parents=True, exist_ok=True)
    path = settings.DATA / "operation.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Another operation holds operation.lock; see docs/mutations.md for crash recovery") from None
    os.close(fd)
    try:
        yield
    finally:
        path.unlink()


def status():
    path = settings.DATA / "active.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"state": "baseline"}


def patch_template(service, template):
    kubectl("patch", "deployment", service, "--type=json", "-p", json.dumps([
        {"op": "replace", "path": "/spec/template", "value": template}]))
    kubectl("rollout", "status", "deployment/" + service, "--timeout=180s")


def apply_override(service, baseline, override_path):
    template = copy.deepcopy(baseline)
    if override_path:
        doc = yaml.safe_load((settings.ROOT / override_path).read_text(encoding="utf-8"))
        entry = doc["services"][service]
        container = template["spec"]["containers"][0]
        if "image" in entry:
            container["image"] = entry["image"]
        env = {e["name"]: e for e in container.get("env", [])}
        for key, value in entry.get("environment", {}).items():
            env[key] = {"name": key, "value": str(value)}
        container["env"] = list(env.values())
        for i, volume in enumerate(entry.get("volumes", [])):
            source, target, _ = volume.rsplit(":", 2)
            # Legacy Windows absolute paths are relocated, never executed as commands.
            normalized = source.replace("\\", "/")
            if "cia_preexperiment_v2/" not in normalized:
                raise ValueError("Mutation source must belong to preserved experiment inputs")
            relative = "cia_preexperiment_v2/" + normalized.split("cia_preexperiment_v2/", 1)[1]
            source_path = settings.ROOT / relative
            name = f"mop-mutation-{i}"
            cm = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name},
                  "data": {"payload": source_path.read_text(encoding="utf-8")}}
            kubectl("apply", "-f", "-", payload=json.dumps(cm))
            mounts = [v for v in container.get("volumeMounts", []) if v["mountPath"] != target]
            mounts.append({"name": name, "mountPath": target, "subPath": "payload", "readOnly": True})
            container["volumeMounts"] = mounts
            volumes = [v for v in template["spec"].get("volumes", []) if v["name"] != name]
            volumes.append({"name": name, "configMap": {"name": name}})
            template["spec"]["volumes"] = volumes
    # Explicitly replace lists through merge patch; never edit original source files.
    patch_template(service, template)


def restore_internal(case_id=None):
    current = status()
    if current.get("state") == "baseline":
        return current
    if case_id and current["case_id"] != case_id:
        raise ValueError("Active case differs from requested restore")
    patch_template(current["service"], current["template"])
    actual = json.loads(kubectl("get", "deployment", current["service"], "-o", "json"))
    if actual["spec"]["template"] != current["template"]:
        raise RuntimeError("Restored deployment template does not match saved baseline")
    (settings.DATA / "active.json").unlink()
    return {"state": "baseline", "restored_case": current["case_id"]}


def restore(case_id=None):
    with exclusive():
        return restore_internal(case_id)


def oracle():
    script = (settings.LEGACY / "src/method/oracle_probe.py").read_text(encoding="utf-8")
    return json.loads(kubectl("exec", "-i", "deployment/recommendationservice", "--", "python", "-", payload=script))


def run(case_id):
    case = case_by_id(case_id)
    if case is None:
        raise ValueError("Unknown mutation")
    with exclusive():
        if status().get("state") != "baseline":
            raise RuntimeError("An unfinished experiment requires restore first")
        service = case["changed_service"]
        deployment = json.loads(kubectl("get", "deployment", service, "-o", "json"))
        baseline = deployment["spec"]["template"]
        experiment_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
        out = settings.DATA / experiment_id
        record = {"id": experiment_id, "case_id": case_id, "change_type": case["change_type"],
                  "service": service, "started": time.time(), "status": "running", "phases": {}}
        save(settings.DATA / "active.json", {"state": "active", "case_id": case_id,
                                             "service": service, "template": baseline})
        save(out / "result.json", record)
        try:
            for phase, override in (("original", case.get("original")), ("changed", case.get("changed"))):
                apply_override(service, baseline, override)
                record["phases"][phase] = collect(out / phase)
                if phase == "original" and case["cohort"] == "controlled" and not record["phases"][phase]["gate_pass"]:
                    raise RuntimeError("Original baseline trace/workload gate failed; mutation was not applied")
                record["phases"][phase]["oracle"] = oracle()
                save(out / "result.json", record)
            before = record["phases"]["original"]["oracle"]
            after = record["phases"]["changed"]["oracle"]
            record["changed_oracle_keys"] = [key for key in before if before[key] != after.get(key)]
            record["status"] = "complete"
        except Exception as exc:
            record.update(status="error", error=str(exc))
        finally:
            try:
                restore_internal(case_id)
                record["restored"] = True
                record["phases"]["restored"] = collect(out / "restored")
                record["baseline_gate_pass"] = record["phases"]["restored"]["gate_pass"]
                if not record["baseline_gate_pass"]:
                    record.update(status="error", error="Restored workload/trace gate failed")
                save(settings.DATA / "latest.json", record["phases"]["restored"]["summary"])
            except Exception as exc:
                record.update(status="restore_failed", restore_error=str(exc))
            record["finished"] = time.time()
            save(out / "result.json", record)
        return record
