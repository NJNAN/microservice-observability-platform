import argparse
import json
import sys
import time

from . import mutations, settings
from .experiments import collect
from .storage import save


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    mutation = sub.add_parser("mutation")
    mutation.add_argument("action", choices=["list", "run", "run-all", "restore", "status"])
    mutation.add_argument("case", nargs="?")
    sub.add_parser("demo")
    args = parser.parse_args()
    if args.command == "demo":
        with mutations.exclusive():
            result = collect(settings.DATA / ("gate-" + str(int(time.time()))))
            save(settings.DATA / "latest.json", result["summary"])
        print(json.dumps(result, indent=2))
        return 0 if result["gate_pass"] else 1
    if args.action == "list":
        result = mutations.catalog()
    elif args.action == "status":
        result = mutations.status()
    elif args.action == "restore":
        result = mutations.restore(args.case)
    elif args.action == "run-all":
        result = []
        for case in mutations.catalog():
            run = mutations.run(case["case_id"])
            result.append(run)
            if run["status"] != "complete":
                break
    else:
        if not args.case:
            parser.error("run requires a case ID")
        result = mutations.run(args.case)
    print(json.dumps(result, indent=2))
    runs = result if args.action == "run-all" else [result]
    return int(any(isinstance(r, dict) and r.get("status") in ("error", "restore_failed") for r in runs))


if __name__ == "__main__":
    sys.exit(main())
