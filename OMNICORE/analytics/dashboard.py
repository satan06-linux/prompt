import os
from typing import Dict, Any

def generate_report(all_scores: Dict[str, Any], config_data: Dict[str, Any], system_metrics: Dict[str, Any], output_path: str):
    """Generates a markdown report for the benchmark run."""
    
    lines = []
    lines.append(f"# Nexafian Prometheus Benchmark Report")
    lines.append(f"**Model Evaluated:** `{config_data['model_id']}`")
    lines.append(f"**Timestamp:** `{config_data['timestamp']}`")
    lines.append("")
    
    total_samples = system_metrics["total_samples"]
    total_latency = system_metrics["total_latency_sec"]
    avg_latency = total_latency / total_samples if total_samples > 0 else 0
    
    lines.append(f"## System Metrics")
    lines.append(f"- **Total Samples Evaluated:** {total_samples}")
    lines.append(f"- **Average Generation Latency:** {avg_latency:.2f}s")
    lines.append("")
    
    lines.append(f"## Domain Leaderboard")
    lines.append("| Domain | Average Score |")
    lines.append("|---|---|")
    
    overall_sum = 0
    valid_domains = 0
    
    for domain, scores in all_scores.items():
        if not scores: continue
        avg_score = sum(s["final_score"] for s in scores) / len(scores)
        overall_sum += avg_score
        valid_domains += 1
        lines.append(f"| {domain.title()} | {avg_score:.2f} / 100 |")
        
    overall_avg = overall_sum / valid_domains if valid_domains > 0 else 0
    lines.append(f"| **Overall Average** | **{overall_avg:.2f} / 100** |")
    lines.append("")
    
    lines.append(f"## Breakdown")
    for domain, scores in all_scores.items():
        if not scores: continue
        lines.append(f"### {domain.title()}")
        for s in scores:
            lines.append(f"- **{s['task_id']}**: {s['final_score']}/100 (File: `{os.path.basename(s['output_file'])}`)")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
