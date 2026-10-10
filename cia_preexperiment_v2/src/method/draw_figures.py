"""Generate ten source-backed standalone SVG figures without plot dependencies."""

import csv
import html
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results/tables/method_experiment"
OUT = ROOT / "results/figures/method_experiment"
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = json.loads((TABLES / "summary.json").read_text(encoding="utf-8"))
with (TABLES / "scores.csv").open(encoding="utf-8", newline="") as file:
    SCORES = list(csv.DictReader(file))
with (TABLES / "case_level_scores.csv").open(encoding="utf-8", newline="") as file:
    CASES = list(csv.DictReader(file))

COLORS = {"B0": "#94a3b8", "B1": "#8b5cf6", "B2": "#2563eb", "B3": "#f59e0b", "B4": "#d97706", "B5": "#059669"}
METHOD_LABELS = {"B0": "Changed only", "B1": "Static reach", "B2": "Strong static", "B3": "Runtime reach", "B4": "Runtime frequency", "B5": "Hybrid"}
FONT = "Segoe UI, Arial, sans-serif"


def esc(value):
    return html.escape(str(value), quote=True)


def base(width, height, title, subtitle):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
            f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
            f'<text x="42" y="43" font-family="{FONT}" font-size="24" font-weight="700" fill="#0f172a">{esc(title)}</text>',
            f'<text x="42" y="68" font-family="{FONT}" font-size="12" fill="#64748b">{esc(subtitle)}</text>']


def text(x, y, value, size=12, color="#334155", anchor="start", weight="400"):
    return f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{esc(value)}</text>'


def save(name, parts):
    parts.append('</svg>')
    (OUT / (name + ".svg")).write_text("\n".join(parts), encoding="utf-8")


def group(cohort, granularity, coverage="high"):
    return next((g for g in SUMMARY["groups"] if (g["cohort"], g["granularity"], g["coverage_level"]) == (cohort, granularity, coverage)), None)


def bar_methods(granularity, name):
    title = f"{granularity.title()} F1 by method"
    parts = base(950, 510, title, "High coverage; each bar is the mean of case-level F1 across three original-trace repetitions")
    cohorts = [x for x in ("controlled", "real_commit_replay") if group(x, granularity)]
    left, bottom, plot_h = 72, 422, 300
    for value in (0, .25, .5, .75, 1):
        y = bottom - value * plot_h
        parts += [f'<line x1="{left}" y1="{y}" x2="910" y2="{y}" stroke="#e2e8f0"/>', text(60, y+4, f"{value:.2f}", 11, anchor="end")]
    methods = list(METHOD_LABELS)
    group_w = 130
    bar_w = 26 if len(cohorts) == 2 else 48
    for i, method in enumerate(methods):
        center = left + 70 + i * group_w
        for j, cohort in enumerate(cohorts):
            value = group(cohort, granularity)["mean_f1"][method]
            x = center - bar_w * len(cohorts) / 2 + j * bar_w
            height = value * plot_h
            color = COLORS[method]
            opacity = "1" if cohort == "controlled" else ".52"
            parts.append(f'<rect x="{x}" y="{bottom-height:.1f}" width="{bar_w-3}" height="{height:.1f}" fill="{color}" opacity="{opacity}" rx="3"/>')
            parts.append(text(x+(bar_w-3)/2, bottom-height-6, f"{value:.2f}", 10, anchor="middle"))
        parts.append(text(center, bottom+24, method, 12, anchor="middle", weight="700"))
        parts.append(text(center, bottom+41, METHOD_LABELS[method], 10, anchor="middle"))
    if len(cohorts) == 2:
        parts += [text(650, 93, "Solid: controlled", 11), text(790, 93, "Pale: commit replay", 11)]
    save(name, parts)


def case_gain():
    rows = [r for r in CASES if r["granularity"] == "service" and r["coverage_level"] == "high"]
    rows.sort(key=lambda r: (r["cohort"], float(r["hybrid_gain"])))
    height = max(340, 112 + len(rows) * 27 + 55)
    parts = base(1050, height, "Case-level hybrid gain", "Service F1; B5 minus best fixed single baseline within each cohort")
    zero, scale = 660, 280
    parts.append(f'<line x1="{zero}" y1="96" x2="{zero}" y2="{height-42}" stroke="#64748b"/>')
    for i, row in enumerate(rows):
        y = 112 + i * 27
        value = float(row["hybrid_gain"])
        width = abs(value) * scale
        x = zero if value >= 0 else zero-width
        color = "#059669" if value > 0 else "#ef4444" if value < 0 else "#94a3b8"
        parts += [text(38, y+12, row["case_id"], 11),
                  f'<rect x="{x:.1f}" y="{y}" width="{max(width,2):.1f}" height="17" fill="{color}" rx="2"/>',
                  text(950, y+12, f"{value:+.3f}", 11, anchor="end")]
    save("03_case_level_hybrid_gain", parts)


def curves(metric, name, title):
    parts = base(950, 510, title, "Actual service coverage from trace-subset workloads; controlled solid, commit replay dashed")
    x0, x1, y0, y1 = 90, 855, 400, 120
    for v in (0, .25, .5, .75, 1):
        y = y0 - v*(y0-y1)
        parts += [f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#e2e8f0"/>', text(76, y+4, f"{v:.2f}", 11, anchor="end")]
        x = x0 + v*(x1-x0)
        parts += [f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="#f1f5f9"/>', text(x, y0+21, f"{v:.2f}", 11, anchor="middle")]
    parts += [text(470, 450, "Service coverage", 12, anchor="middle")]
    series = (("B2", "Strong static"), ("runtime_best", "Best runtime"), ("B5", "Hybrid"))
    for cohort in ("controlled", "real_commit_replay"):
        for method, label in series:
            points = []
            for level in ("low", "medium", "high"):
                cov = next((c for c in SUMMARY["coverage"] if c["cohort"] == cohort and c["coverage_level"] == level), None)
                if not cov: continue
                actual_method = group(cohort, "service", level)["best_runtime"] if method == "runtime_best" else method
                subset = [r for r in SCORES if r["cohort"] == cohort and r["coverage_level"] == level and r["granularity"] == "service" and r["method"] == actual_method]
                if not subset: continue
                value = sum(float(r[metric]) for r in subset)/len(subset)
                points.append((x0+cov["service_coverage"]*(x1-x0), y0-value*(y0-y1)))
            if not points: continue
            dash = '' if cohort == 'controlled' else ' stroke-dasharray="8 5"'
            coords = " ".join(f"{x:.1f},{y:.1f}" for x,y in points)
            color = COLORS["B4"] if method == "runtime_best" else COLORS[method]
            parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash}/>' )
            parts.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>' for x,y in points)
    for i,(method,label) in enumerate(series):
        x = 110+i*230
        color = COLORS["B4"] if method == "runtime_best" else COLORS[method]
        parts += [f'<line x1="{x}" y1="88" x2="{x+28}" y2="88" stroke="{color}" stroke-width="4"/>', text(x+35, 92, label, 11)]
    save(name, parts)


def error_chart(field_total, field_change, name, title):
    parts = base(950, 460, title, "Unique case-object counts using the first repetition at each coverage level")
    rows = [r for r in SUMMARY["errors"] if r["granularity"] == "service"]
    labels = [(r["cohort"], r["coverage_level"], r[field_total], r[field_change]) for r in rows]
    max_value = max((total for _,_,total,_ in labels), default=1) or 1
    for i,(cohort,level,total,changed) in enumerate(labels):
        y = 110+i*48
        width = 500*total/max_value
        changed_width = 500*changed/max_value
        parts += [text(38, y+15, f"{cohort[:10]} / {level}", 12),
                  f'<rect x="225" y="{y}" width="{width:.1f}" height="24" fill="#cbd5e1" rx="3"/>',
                  f'<rect x="225" y="{y}" width="{changed_width:.1f}" height="24" fill="#059669" rx="3"/>',
                  text(740, y+17, f"{changed} / {total}", 12)]
    parts += [f'<rect x="38" y="{420}" width="15" height="15" fill="#059669"/>', text(60, 433, "Corrected / recovered", 11),
              f'<rect x="240" y="{420}" width="15" height="15" fill="#cbd5e1"/>', text(262, 433, "Total original errors", 11)]
    save(name, parts)


def gain_by_change_type():
    rows = [r for r in CASES if r["cohort"] == "controlled" and r["coverage_level"] == "high"]
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row["change_type"], row["granularity"])].append(float(row["hybrid_gain"]))
    types = sorted({key[0] for key in buckets})
    parts = base(950, 480, "Hybrid gain by change type", "High coverage; mean B5 minus best fixed single baseline")
    zero, scale = 275, 400
    parts.append(f'<line x1="{zero}" y1="106" x2="{zero}" y2="{438}" stroke="#64748b"/>')
    for i,kind in enumerate(types):
        y = 120+i*59
        parts.append(text(38,y+22,kind,12))
        for j,gran in enumerate(("service","api")):
            vals = buckets.get((kind,gran),[])
            if not vals: continue
            value = sum(vals)/len(vals)
            width = abs(value)*scale
            x = zero if value>=0 else zero-width
            color = "#059669" if gran=="service" else "#2563eb"
            parts += [f'<rect x="{x:.1f}" y="{y+j*20}" width="{max(width,2):.1f}" height="15" fill="{color}" rx="2"/>',
                      text(730,y+j*20+12,f"{gran}: {value:+.3f} (n={len(vals)})",11)]
    save("09_gain_by_change_type",parts)


def controlled_vs_real():
    parts = base(950,460,"Controlled vs real commit replay","High coverage; means are kept separate by cohort")
    cohorts = ("controlled", "real_commit_replay")
    zero, scale = 290, 450
    parts.append(f'<line x1="{zero}" y1="105" x2="{zero}" y2="415" stroke="#64748b"/>')
    for i,cohort in enumerate(cohorts):
        for j,gran in enumerate(("service","api")):
            y=125+i*125+j*42
            g=group(cohort,gran)
            parts.append(text(40,y+16,f"{cohort} / {gran}",12))
            if g is None:
                parts.append(text(310,y+16,"No valid cases",12,"#ef4444"))
                continue
            value=g["hybrid_minus_best_single_mean"]
            width=abs(value)*scale
            x=zero if value>=0 else zero-width
            color="#059669" if value>=0 else "#ef4444"
            parts += [f'<rect x="{x:.1f}" y="{y}" width="{max(width,2):.1f}" height="23" fill="{color}" rx="3"/>',
                      text(780,y+16,f"{value:+.3f}  n={g['case_count']}",12)]
    save("10_controlled_vs_real",parts)


def main():
    bar_methods("service","01_service_f1_by_method")
    bar_methods("api","02_api_f1_by_method")
    case_gain()
    curves("f1","04_f1_vs_coverage","F1 versus runtime coverage")
    curves("recall","05_recall_vs_coverage","Recall versus runtime coverage")
    curves("precision","06_precision_vs_coverage","Precision versus runtime coverage")
    error_chart("static_fp","static_fp_corrected","07_static_fp_correction","Static false positives corrected")
    error_chart("runtime_fn","runtime_fn_recovered","08_runtime_fn_recovery","Runtime false negatives recovered")
    gain_by_change_type()
    controlled_vs_real()
    print(json.dumps({"figure_count":len(list(OUT.glob("*.svg"))),"directory":str(OUT)},indent=2))


if __name__=="__main__":
    main()
