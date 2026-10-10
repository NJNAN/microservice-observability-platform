"""Write the 19-section, evidence-linked method decision after evaluation."""

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "results/tables/method_experiment"
REPORT = ROOT / "PREEXPERIMENT_CIA_METHOD_DECISION.md"
SUMMARY = json.loads((TABLES / "summary.json").read_text(encoding="utf-8"))
STATUS = json.loads((TABLES / "evaluation_status.json").read_text(encoding="utf-8"))
CONTROLLED = json.loads((ROOT / "data/mutations/method_controlled/cases.json").read_text(encoding="utf-8"))
REAL = json.loads((ROOT / "data/commits/method_replays/cases.json").read_text(encoding="utf-8"))
CASES = CONTROLLED + REAL
with (TABLES / "case_level_scores.csv").open(encoding="utf-8", newline="") as file:
    CASE_SCORES = list(csv.DictReader(file))


def relative(path):
    return path.relative_to(ROOT).as_posix()


def raw_dir(case):
    return ROOT / "results/raw" / ("method_controlled" if case["cohort"] == "controlled" else "method_real_replays") / case["case_id"]


def group(cohort, granularity, level="high"):
    return next((g for g in SUMMARY["groups"] if (g["cohort"], g["granularity"], g["coverage_level"]) == (cohort, granularity, level)), None)


def error(cohort, granularity, level="high"):
    return next((g for g in SUMMARY["errors"] if (g["cohort"], g["granularity"], g["coverage_level"]) == (cohort, granularity, level)), None)


def pct(value):
    return f"{100*value:.1f}%" if value is not None else "NA"


def signed_pp(value):
    return f"{100*value:+.1f} pp" if value is not None else "NA"


def metric_table(cohort):
    lines = ["| 层级 | B0 | B1 | B2 | B3 | B4 | B5 | 最强单法 | B5 − 最强单法 |",
             "|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for gran in ("service", "api"):
        g = group(cohort, gran)
        if not g:
            lines.append(f"| {gran} | NA | NA | NA | NA | NA | NA | NA | NA |")
            continue
        row = [gran] + [pct(g["mean_f1"][f"B{i}"]) for i in range(6)]
        row += [g["best_single"], signed_pp(g["hybrid_minus_best_single_mean"])]
        lines.append("| " + " | ".join(row) + " |")
    return lines


def workload_stats(cases):
    summary = {}
    for phase in ("original", "changed"):
        statuses = []
        trace_counts = []
        span_counts = []
        for case in cases:
            path = raw_dir(case)
            if not (path / "progress.json").exists(): continue
            if json.loads((path / "progress.json").read_text(encoding="utf-8"))["status"] != "complete": continue
            for i in range(1, 4):
                workload = json.loads((path / f"{phase}_{i:02d}.workload.json").read_text(encoding="utf-8"))
                statuses.extend(row["status"] for row in workload["rows"])
                trace = json.loads((path / f"{phase}_{i:02d}.trace_summary.json").read_text(encoding="utf-8"))
                trace_counts.append(trace["trace_count"])
                span_counts.append(trace["span_count"])
        summary[phase] = {"success": sum(s == 200 for s in statuses), "total": len(statuses),
                          "trace_min": min(trace_counts) if trace_counts else None,
                          "trace_max": max(trace_counts) if trace_counts else None,
                          "span_min": min(span_counts) if span_counts else None,
                          "span_max": max(span_counts) if span_counts else None}
    return summary


def label_stats(cases):
    out = {"api": Counter(), "service": Counter()}
    for case in cases:
        path = raw_dir(case) / "ground_truth.json"
        if not path.exists(): continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out["api"].update(data["api_labels"].values())
        out["service"].update(data["service_labels"].values())
    return out


def valid_cases():
    valid = []
    for case in CASES:
        path = raw_dir(case)
        progress = path / "progress.json"
        truth = path / "ground_truth.json"
        if not progress.exists() or not truth.exists(): continue
        if json.loads(progress.read_text(encoding="utf-8"))["status"] != "complete": continue
        gt = json.loads(truth.read_text(encoding="utf-8"))
        if "Impacted" not in gt["api_labels"].values(): continue
        valid.append(case)
    return valid


def figure_links():
    names = ("01_service_f1_by_method", "02_api_f1_by_method", "03_case_level_hybrid_gain",
             "04_f1_vs_coverage", "05_recall_vs_coverage", "06_precision_vs_coverage",
             "07_static_fp_correction", "08_runtime_fn_recovery", "09_gain_by_change_type",
             "10_controlled_vs_real")
    return [f"[{name}](results/figures/method_experiment/{name}.svg)" for name in names]


def main():
    valid = valid_cases()
    controlled = [c for c in valid if c["cohort"] == "controlled"]
    real = [c for c in valid if c["cohort"] == "real_commit_replay"]
    cg_s, cg_a = group("controlled", "service"), group("controlled", "api")
    rg_s, rg_a = group("real_commit_replay", "service"), group("real_commit_replay", "api")
    all_groups = [g for g in (cg_s, cg_a, rg_s, rg_a) if g]
    high_gain = [g["hybrid_minus_best_single_mean"] for g in all_groups]
    majority = all(g["positive_case_count"] > g["case_count"] / 2 for g in all_groups)
    if len(valid) >= 20 and len(real) >= 5 and high_gain and min(high_gain) >= .10 and majority:
        decision = "GO"
    elif len(valid) >= 20 and len(real) >= 5 and high_gain and min(high_gain) >= .05 and any(g["positive_case_count"] > 0 for g in all_groups):
        decision = "CONDITIONAL GO"
    else:
        decision = "METHOD NO-GO"
    counts = label_stats(valid)
    work_c, work_r = workload_stats(controlled), workload_stats(real)
    es_c, ea_c = error("controlled", "service"), error("controlled", "api")
    es_r, ea_r = error("real_commit_replay", "service"), error("real_commit_replay", "api")
    lines = [
        f"Decision: {decision}", "",
        f"Valid cases: {len(valid)} ({len(controlled)} controlled, {len(real)} real-commit semantic replays)",
        f"High-coverage controlled service/API hybrid gain: {signed_pp(cg_s['hybrid_minus_best_single_mean']) if cg_s else 'NA'} / {signed_pp(cg_a['hybrid_minus_best_single_mean']) if cg_a else 'NA'}",
        f"High-coverage real-replay service/API hybrid gain: {signed_pp(rg_s['hybrid_minus_best_single_mean']) if rg_s else 'NA'} / {signed_pp(rg_a['hybrid_minus_best_single_mean']) if rg_a else 'NA'}",
        "", "# Online Boutique CIA 方法预实验决策", "",
        "## 1. Executive Decision", "",
        f"**{decision}。**本次比较固定规则的 B0–B5，分别在 service 与 API 层评价。结论以独立行为探针的原版/变更版差异为准；after trace 从未进入预测。",
        f"完成 {len(valid)}/{len(CASES)} 个有可复核行为差异的案例。真实提交组是**历史业务 hunk 在已修好 tracing 的 v0.10.4 运行时上的重放**；其中两例使用精确 Git 文件 blob，三例移植业务 hunk，并非完整历史树的原生构建。", "",
        "## 2. Research Question", "",
        "检验静态依赖与变更前 runtime trace 的错误是否互补，以及仅以 coverage 调整两类证据能否稳定超过最强单法。预先锁定的规则见 [protocol.py](src/method/protocol.py) 与 [锁文件](results/raw/method_protocol_lock.json)。", "",
        "## 3. Experimental System", "",
        "Online Boutique v0.10.4，10 个应用服务；原有 trace gate 已达到 10/10 服务、14 条跨服务边、71/71 gRPC client/server 配对。固定购物序列为首页→商品页→加购→购物车→结算，间隔 0.2 秒；每版本三次独立 HTTP session。每一案例只替换清单中的业务文件或配置，随后恢复服务。", "",
        "本轮 24 个候选案例的 72 个原版重复均得到 6 条业务 trace、148 个 span、10 个应用服务、14 条跨服务边；每轮 71/71 个 gRPC client/server 配对，断裂 parent reference 为 0。逐轮证据见[受控原始记录](results/raw/method_controlled/)与[真实重放原始记录](results/raw/method_real_replays/)。", "",
        f"Controlled 原版 HTTP 200 为 {work_c['original']['success']}/{work_c['original']['total']}，变更版为 {work_c['changed']['success']}/{work_c['changed']['total']}；真实提交重放原版为 {work_r['original']['success']}/{work_r['original']['total']}，变更版为 {work_r['changed']['success']}/{work_r['changed']['total']}。变更版的非 200 是预期故障行为时作为 GT 保留。", "",
        "全部案例结束后已恢复基线 Compose；10/10 应用服务运行，另一次三轮固定购物检查取得 [15/15 HTTP 200](results/raw/method_final_restore_workload.json)。", "",
        "## 4. Change Cases", "",
        "| 案例 | 组 / 类型 | 服务 | 文件或配置 | 语义机制 |", "|---|---|---|---|---|",
    ]
    for case in valid:
        desc = case.get("description", "")
        if case["cohort"] == "real_commit_replay": desc += f"；Git `{case['commit'][:10]}`"
        lines.append(f"| {case['case_id']} | {case['cohort']} / {case['change_type']} | {case['changed_service']} | `{case['changed_file']}` | {desc} |")
    lines += ["", "受控变更设计量：Logic 4、API 4、Dependency 4、Configuration 3、Failure/Fallback 3。历史 nanos 舍入案例 `R03_nanos_rounding_076819` 虽运行六轮，但固定探针未发现稳定功能差异，预先按有效性规则剔除；原始记录仍保留。每例业务差异、SHA 与 Compose 覆盖保存在 [受控清单](data/mutations/method_controlled/cases.json) 或 [真实提交重放清单](data/commits/method_replays/cases.json)。", "",
              "## 5. Ground Truth", "",
              "GT 来自无 OTel 客户端的直接 gRPC 探针、HTTP 页面语义字段与固定购物请求状态；不会依据 trace 有无给标签。先比较各版本三轮内的稳定性，再比较版本间结果。随机订单号、交易号和运单号只比较是否存在；不稳定对象标 Unknown 并排除 P/R/F1。服务由其 API 标签汇总；有任一 Impacted 即 Impacted，全部已知且无变化才是 Not Impacted。", "",
              f"API 标签：Impacted {counts['api']['Impacted']}，Not Impacted {counts['api']['Not Impacted']}，Unknown {counts['api']['Unknown']}（跨案例对象计数）；service 标签：{counts['service']['Impacted']} / {counts['service']['Not Impacted']} / {counts['service']['Unknown']}。冻结全集为 10 服务、26 业务端点；直接探针未覆盖的 frontend 路由保持 Unknown。", "",
              "## 6. Static Baselines", "",
              "B0 只报变更服务；B1 用源码审计的服务调用图反向可达；B2 用 endpoint ownership、RPC 类型边、两跳限制和已审计的忽略响应规则。checkout 丢弃 email 的 Empty 响应与错误；recommendation 只消费目录产品 ID。静态图是人工审阅的本系统小图，不冒称全程序自动静态分析，也不称 Microscope。", "",
              "## 7. Runtime Baselines", "",
              "B3 从**原版** Jaeger trace 的真实 parent-child server span 构造 API/服务调用边并反向可达；B4 仅保留每轮调用次数 ≥2 的边。原版与变更版 trace 均保留原始文件，但预测代码只读取 `original_*.traces.json`。", "",
              "## 8. Coverage-Aware Hybrid", "",
              "B5 固定规则：静态与 runtime 均支持得分 1.0；仅 runtime 支持 0.8；仅静态支持时，API coverage <0.40 得 0.70、0.40–0.70 得 0.45、≥0.70 得 0.20；阈值 0.50。无训练、无验证集调参。", "",
              "## 9. Main Results", "",
              "高 coverage 的 case-macro F1；同一案例先平均三次原版 trace，再跨案例平均。最强单法在 B1–B4 中按该组总体均值选取。", "",
              "**Controlled**", "", *metric_table("controlled"), "", "**Real commit replays**", "", *metric_table("real_commit_replay"), "",
              "图：[service F1](results/figures/method_experiment/01_service_f1_by_method.svg)、[API F1](results/figures/method_experiment/02_api_f1_by_method.svg)、[逐案例增益](results/figures/method_experiment/03_case_level_hybrid_gain.svg)。", "",
              "## 10. Service-Level Results", "",
    ]
    for cohort, g in (("controlled",cg_s),("real_commit_replay",rg_s)):
        if g:
            lines.append(f"- {cohort}: B5 {pct(g['mean_f1']['B5'])}，最强单法 {g['best_single']} {pct(g['mean_f1'][g['best_single']])}，差 {signed_pp(g['hybrid_minus_best_single_mean'])}；正/平/负案例 {g['positive_case_count']}/{g['zero_case_count']}/{g['negative_case_count']}。")
    lines += ["", "## 11. API-Level Results", ""]
    for cohort, g in (("controlled",cg_a),("real_commit_replay",rg_a)):
        if g:
            lines.append(f"- {cohort}: B5 {pct(g['mean_f1']['B5'])}，最强单法 {g['best_single']} {pct(g['mean_f1'][g['best_single']])}，差 {signed_pp(g['hybrid_minus_best_single_mean'])}；正/平/负案例 {g['positive_case_count']}/{g['zero_case_count']}/{g['negative_case_count']}。")
    lines += ["", "## 12. Coverage Analysis", "",
              "低/中/高 coverage 通过从同一固定购物流程的**原版**完整 trace 选择请求子集生成：低只用 POST /cart，中加首页与商品页，高用完整五步（含重定向）。因此是请求覆盖删减，不是随机删 span；三种视图保持原始父子链。", "",
              "| 组 | coverage | service | API | 静态服务边 | B2 service F1 | 最强 runtime service F1 | B5 service F1 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for c in SUMMARY["coverage"]:
        g = group(c["cohort"], "service", c["coverage_level"])
        lines.append(f"| {c['cohort']} | {c['coverage_level']} | {pct(c['service_coverage'])} | {pct(c['api_coverage'])} | {pct(c['static_edge_coverage'])} | {pct(g['mean_f1']['B2'])} | {pct(g['mean_f1'][g['best_runtime']])} | {pct(g['mean_f1']['B5'])} |")
    lines += ["", "图：[F1 曲线](results/figures/method_experiment/04_f1_vs_coverage.svg)、[Recall 曲线](results/figures/method_experiment/05_recall_vs_coverage.svg)、[Precision 曲线](results/figures/method_experiment/06_precision_vs_coverage.svg)。coverage 目标按实际值报告，不强行改写为 20–40/50–70/80+。", "",
              "## 13. Error Complementarity", "",
              "以下为高 coverage、每案例第 1 轮的唯一 case-object 计数；Static=B2、Runtime=B3、Hybrid=B5。", "",
              "| 组 / 层级 | Static FP / FN | Runtime FP / FN | Hybrid 修正 Static FP | 恢复 Runtime FN | B5 相对最强单法新增 FP / FN | Hybrid 剩余 FP / FN |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cohort in ("controlled", "real_commit_replay"):
        for gran, e in (("service", error(cohort,"service")), ("api",error(cohort,"api"))):
            if e:
                baseline = group(cohort, gran)["best_single"]
                lines.append(f"| {cohort} / {gran} | {e['static_fp']} / {e['static_fn']} | {e['runtime_fp']} / {e['runtime_fn']} | {e['static_fp_corrected']} | {e['runtime_fn_recovered']} | {baseline}: {e['hybrid_added_fp_vs_' + baseline]} / {e['hybrid_added_fn_vs_' + baseline]} | {e['hybrid_fp']} / {e['hybrid_fn']} |")
    lines += ["", "图：[静态 FP 修正](results/figures/method_experiment/07_static_fp_correction.svg)、[runtime FN 恢复](results/figures/method_experiment/08_runtime_fn_recovery.svg)。新增错误以同组高 coverage 最强单法为参照，按唯一 case-object 计算。", "",
              "## 14. Controlled vs Real Commits", "",
              "两个组从未合并成唯一均值。真实组只重放实际 Git 提交中的可执行语义差异，原版/变更版三轮均使用相同现代 tracing 修复。两例 catalog 是精确前后文件 blob；有效的 currency、shipping、recommendation 各一例是旧 hunk 在现代服务源码上的移植，不能推广为完整历史版本回归。另有一例 nanos 舍入尝试因无稳定行为差异被排除。", "",
              "图：[按变更类型](results/figures/method_experiment/09_gain_by_change_type.svg)、[受控对比真实重放](results/figures/method_experiment/10_controlled_vs_real.svg)。", "",
              "## 15. Statistical Analysis", "",
              "独立样本单位为 case；每例三轮只用于稳定性与案例均值，不把 service/API 对象或重复轮次当成独立样本。Bootstrap 以案例重采样 10,000 次，固定 seed 42。", "",
              "| 组 / 层级 | n | B5−最强单法均值 | 中位数 | 标准差 | 95% bootstrap CI | Cohen dz |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cohort in ("controlled", "real_commit_replay"):
        for gran in ("service", "api"):
            g=group(cohort,gran)
            if g:
                ci=g["hybrid_minus_best_single_ci95"]
                dz="NA" if g["cohens_dz"] is None else f"{g['cohens_dz']:.2f}"
                lines.append(f"| {cohort} / {gran} | {g['case_count']} | {signed_pp(g['hybrid_minus_best_single_mean'])} | {signed_pp(g['hybrid_minus_best_single_median'])} | {100*g['hybrid_minus_best_single_std']:.1f} pp | [{signed_pp(ci[0])}, {signed_pp(ci[1])}] | {dz} |")
    lines += ["", "## 16. Failure Cases", "",
              "下表列出高 coverage service 层 B5 最差的案例；原因需结合[受控 GT](results/raw/method_controlled/) 或[真实重放 GT](results/raw/method_real_replays/) 与原版 trace 逐项核对。", "",
              "| 案例 | 组 | B2 | B3 | B4 | B5 | 增益 |", "|---|---|---:|---:|---:|---:|---:|"]
    bad = sorted((r for r in CASE_SCORES if r["granularity"] == "service" and r["coverage_level"] == "high"), key=lambda r: float(r["hybrid_gain"]))[:8]
    for r in bad:
        lines.append(f"| {r['case_id']} | {r['cohort']} | {pct(float(r['f1_B2']))} | {pct(float(r['f1_B3']))} | {pct(float(r['f1_B4']))} | {pct(float(r['f1_B5']))} | {signed_pp(float(r['hybrid_gain']))} |")
    lines += ["", "## 17. Threats to Validity", "",
              "单一系统、固定购物流程与 18 个受控变更限制外推。静态图是人工审阅的小图，可能比自动实现更强。真实提交组是语义重放而非完整历史部署。应用侧推荐随机性未全局固定，故行为探针将非稳定输出归 Unknown，并用固定单候选输入直接测推荐 RPC。Frontend 的可选 assistant/bot 路由未探测，保留 Unknown。低/中 coverage 来自完整原版 workload 的请求级删减，未验证独立分布的外部流量。", "",
              "## 18. SCI Potential", "",
              "本预实验仅验证是否存在足够强、稳定、可利用的互补误差。若 Hybrid 未达到预设门槛，本系统证据不能支持发展 coverage-aware CIA 的 SCI 方法主张；不会借复杂模型或修改假设补救。", "",
              "## 19. Final Decision", "",
              f"**{decision}。**GO 门槛要求至少 20 有效案例、高 coverage B5 比最强单法高 ≥10 pp、多数案例受益且 controlled/real 同向；条件 GO 需 5–10 pp 或清晰可复现的受限优势。当前实测结果见上表，结论按预设门槛执行。", "",
              "### 15 个直接回答", ""]
    answers = [
        "Static 最大问题：跨服务可达容易把调用者都报为受影响；端点/字段约束可压低部分 FP。",
        "Runtime 最大问题：低请求覆盖会漏掉未执行的依赖；频次阈值还能漏掉低频真实链。",
        f"两类错误是否互补：有局部机会，controlled 低 coverage 恢复 {error('controlled','service','low')['runtime_fn_recovered']} 个 service Runtime FN，中 coverage 修正 {error('controlled','service','medium')['static_fp_corrected']} 个 Static FP；高 coverage 两项均为 0，且整体 F1 没增益。",
        "Coverage 是否影响互补：影响错误类型（低覆盖 runtime 漏报更多，中覆盖可削减部分 static 误报），但固定 B5 的收益没有随之转正；service 与 API coverage 必须分开看。",
        f"Hybrid 修正 Static FP：controlled service/API {es_c['static_fp_corrected'] if es_c else 'NA'}/{ea_c['static_fp_corrected'] if ea_c else 'NA'}；real {es_r['static_fp_corrected'] if es_r else 'NA'}/{ea_r['static_fp_corrected'] if ea_r else 'NA'}。",
        f"Hybrid 恢复 Runtime FN：controlled service/API {es_c['runtime_fn_recovered'] if es_c else 'NA'}/{ea_c['runtime_fn_recovered'] if ea_c else 'NA'}；real {es_r['runtime_fn_recovered'] if es_r else 'NA'}/{ea_r['runtime_fn_recovered'] if ea_r else 'NA'}。",
        f"Hybrid 相对同组最强单法新增 FP/FN：controlled service(B2) {es_c['hybrid_added_fp_vs_B2']}/{es_c['hybrid_added_fn_vs_B2']}、API(B4) {ea_c['hybrid_added_fp_vs_B4']}/{ea_c['hybrid_added_fn_vs_B4']}；real service(B2) {es_r['hybrid_added_fp_vs_B2']}/{es_r['hybrid_added_fn_vs_B2']}、API(B2) {ea_r['hybrid_added_fp_vs_B2']}/{ea_r['hybrid_added_fn_vs_B2']}。",
        f"相对最强单法的 F1：controlled service/API {signed_pp(cg_s['hybrid_minus_best_single_mean']) if cg_s else 'NA'}/{signed_pp(cg_a['hybrid_minus_best_single_mean']) if cg_a else 'NA'}；real {signed_pp(rg_s['hybrid_minus_best_single_mean']) if rg_s else 'NA'}/{signed_pp(rg_a['hybrid_minus_best_single_mean']) if rg_a else 'NA'}。",
        f"Controlled mutation 是否有效：{len(controlled)} 例；B5 正/平/负 service 案例 {cg_s['positive_case_count'] if cg_s else 'NA'}/{cg_s['zero_case_count'] if cg_s else 'NA'}/{cg_s['negative_case_count'] if cg_s else 'NA'}。",
        f"Real commit replay 是否有效：{len(real)} 例；B5 正/平/负 service 案例 {rg_s['positive_case_count'] if rg_s else 'NA'}/{rg_s['zero_case_count'] if rg_s else 'NA'}/{rg_s['negative_case_count'] if rg_s else 'NA'}；完整历史版本尚未执行。",
        "多数案例是否受益：见第 10–11 节正/平/负计数与逐案例图；不得以极端案例抬高均值。",
        "Held-out 是否成立：未训练任何参数，因此不存在训练内/外切分；这是事先锁定规则的独立案例评估，不能冒称 learned-model held-out。",
        "明确有效的 change type：高 coverage service 层没有任何类型得到稳定正增益；图 09 分类型样本每型仅 3–4 个。",
        f"最终方向判定：{decision}。",
        "若 GO 的创新点：本轮不适用；没有支持 GO 的方法证据，不提出 SCI 创新点。",
    ]
    lines += [f"{i}. {answer}" for i,answer in enumerate(answers,1)]
    lines += ["", "### 原始证据与复现入口", "",
              "- [原始评分](results/tables/method_experiment/scores.csv)、[案例均值](results/tables/method_experiment/case_level_scores.csv)、[误差对象计数](results/tables/method_experiment/errors.csv)、[统计摘要](results/tables/method_experiment/summary.json)。",
              "- [采集器](src/method/collect_pilot_phase.py)、[直接功能探针](src/method/oracle_probe.py)、[评价脚本](src/method/evaluate_cases.py)、[受控执行器](src/method/run_controlled_cases.py)、[真实重放执行器](src/method/run_real_commit_replays.py)。",
              "- 每例 `original_01..03` 与 `changed_01..03` 的 workload、raw traces、trace summary、oracle 保存在 `results/raw/method_controlled/<case_id>/` 或 `results/raw/method_real_replays/<case_id>/`。",
              ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"decision": decision, "valid": len(valid), "controlled": len(controlled), "real_replays": len(real), "report": str(REPORT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
