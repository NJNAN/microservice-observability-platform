"""Case-level, cohort-separated scores and paired bootstrap intervals."""

import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results/tables/method_experiment"
SEED = 42


def read_csv(name):
    with (TABLES / name).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def mean(values):
    return statistics.mean(values) if values else None


def bootstrap_ci(values, repeats=10000):
    if not values:
        return [None, None]
    rng = random.Random(SEED)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(repeats)]
    samples.sort()
    return [samples[int(0.025 * repeats)], samples[int(0.975 * repeats)]]


def main():
    scores = read_csv("scores.csv")
    errors = read_csv("errors.csv")
    case_types = {row["case_id"]: row["change_type"] for row in scores}
    cases = defaultdict(list)
    for row in scores:
        key = (row["cohort"], row["granularity"], row["coverage_level"], row["case_id"], row["method"])
        cases[key].append(float(row["f1"]))
    case_means = {key: mean(values) for key, values in cases.items()}
    cohorts = sorted({key[0] for key in case_means})
    group_summary = []
    per_case_rows = []
    for cohort in cohorts:
        for granularity in ("service", "api"):
            for coverage in ("low", "medium", "high"):
                case_ids = sorted({key[3] for key in case_means if key[:3] == (cohort, granularity, coverage)})
                if not case_ids:
                    continue
                by_method = {method: [case_means[(cohort, granularity, coverage, case_id, method)] for case_id in case_ids]
                             for method in ("B0", "B1", "B2", "B3", "B4", "B5")}
                best_static = max(("B1", "B2"), key=lambda method: mean(by_method[method]))
                best_runtime = max(("B3", "B4"), key=lambda method: mean(by_method[method]))
                best_single = max((best_static, best_runtime), key=lambda method: mean(by_method[method]))
                differences = [h - b for h, b in zip(by_method["B5"], by_method[best_single])]
                conservative = [h - max(by_method[m][i] for m in ("B1", "B2", "B3", "B4"))
                                for i, h in enumerate(by_method["B5"])]
                std_diff = statistics.stdev(differences) if len(differences) > 1 else 0.0
                group_summary.append({
                    "cohort": cohort, "granularity": granularity, "coverage_level": coverage,
                    "case_count": len(case_ids),
                    "mean_f1": {method: mean(values) for method, values in by_method.items()},
                    "best_static": best_static, "best_runtime": best_runtime, "best_single": best_single,
                    "hybrid_minus_best_single_mean": mean(differences),
                    "hybrid_minus_best_single_median": statistics.median(differences),
                    "hybrid_minus_best_single_std": std_diff,
                    "hybrid_minus_best_single_ci95": bootstrap_ci(differences),
                    "cohens_dz": mean(differences) / std_diff if std_diff else None,
                    "positive_case_count": sum(x > 1e-9 for x in differences),
                    "zero_case_count": sum(abs(x) <= 1e-9 for x in differences),
                    "negative_case_count": sum(x < -1e-9 for x in differences),
                    "conservative_case_oracle_best_mean": mean(conservative),
                })
                for i, case_id in enumerate(case_ids):
                    per_case_rows.append({
                        "case_id": case_id, "cohort": cohort, "change_type": case_types[case_id], "granularity": granularity,
                        "coverage_level": coverage,
                        **{f"f1_{method}": by_method[method][i] for method in by_method},
                        "best_single": best_single,
                        "hybrid_gain": differences[i],
                        "hybrid_gain_vs_case_oracle_best": conservative[i],
                    })
    coverage_summary = []
    for cohort in cohorts:
        for level in ("low", "medium", "high"):
            subset = [row for row in scores if row["cohort"] == cohort and row["coverage_level"] == level
                      and row["granularity"] == "service" and row["method"] == "B0"]
            if subset:
                coverage_summary.append({"cohort": cohort, "coverage_level": level,
                                         **{metric: mean([float(row[metric]) for row in subset])
                                            for metric in ("service_coverage", "api_coverage", "static_edge_coverage")}})
    error_summary = []
    for cohort in cohorts:
        for granularity in ("service", "api"):
            for level in ("low", "medium", "high"):
                # First repetition per case: counts are unique case-object errors.
                subset = [row for row in errors if row["cohort"] == cohort and row["granularity"] == granularity
                          and row["coverage_level"] == level and row["repeat"] == "1"]
                if subset:
                    error_summary.append({"cohort": cohort, "granularity": granularity,
                                          "coverage_level": level, "case_count": len(subset),
                                          **{field: sum(int(row[field]) for row in subset) for field in (
                                              "static_fp", "static_fn", "runtime_fp", "runtime_fn",
                                              "static_fp_corrected", "runtime_fn_recovered",
                                              "hybrid_induced_fp", "hybrid_induced_fn", "hybrid_fp", "hybrid_fn",
                                              "hybrid_added_fp_vs_B2", "hybrid_added_fn_vs_B2",
                                              "hybrid_added_fp_vs_B4", "hybrid_added_fn_vs_B4")}})
    result = {"groups": group_summary, "coverage": coverage_summary, "errors": error_summary,
              "notes": "Case is the independent unit; F1 is first averaged across its three pre-change trace repetitions. Bootstrap resamples cases with seed 42."}
    (TABLES / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (TABLES / "case_level_scores.csv").open("w", encoding="utf-8", newline="") as file:
        if per_case_rows:
            writer = csv.DictWriter(file, fieldnames=list(per_case_rows[0]))
            writer.writeheader()
            writer.writerows(per_case_rows)
    print(json.dumps({"groups": len(group_summary), "case_rows": len(per_case_rows), "high_service": [g for g in group_summary if g["coverage_level"] == "high" and g["granularity"] == "service"]}, indent=2))


if __name__ == "__main__":
    main()
