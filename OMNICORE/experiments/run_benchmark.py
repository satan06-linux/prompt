import os
import sys
import json
import time
from datetime import datetime, timezone
import pathlib

# Fix Windows encoding issues globally
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from prometheus.providers.openrouter import OpenRouterProvider
from prometheus.evaluators.composite import CompositeEvaluator
from prometheus.analytics.dashboard import generate_report

BENCHMARK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "benchmark", "v1")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")

def run_experiment(model_id: str, provider, max_samples_per_domain: int = 10):
    print(f"🚀 Starting Benchmark Experiment for {model_id}...")
    
    # 1. Setup Versioning & Dirs
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    run_dir = os.path.join(RESULTS_DIR, model_id.replace("/", "_"), f"run_{run_timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    
    # Initialize Evaluator (using OpenRouter as the Judge)
    judge_provider = OpenRouterProvider(model="google/gemini-2.5-flash")
    evaluator = CompositeEvaluator(judge_provider)
    
    domains = [d for d in os.listdir(BENCHMARK_DIR) if os.path.isdir(os.path.join(BENCHMARK_DIR, d))]
    
    all_scores = {}
    config_data = {
        "model_id": model_id,
        "timestamp": run_timestamp,
        "provider": provider.get_metadata(),
        "domains_evaluated": domains
    }
    
    system_metrics = {
        "start_time": time.time(),
        "total_latency_sec": 0,
        "total_samples": 0
    }
    
    # 2. Iterate Benchmark
    for domain in domains:
        dataset_path = os.path.join(BENCHMARK_DIR, domain, "dataset.json")
        rubric_path = os.path.join(BENCHMARK_DIR, domain, "rubric.json")
        
        if not os.path.exists(dataset_path): continue
        
        with open(dataset_path, "r", encoding="utf-8") as f:
            samples = json.load(f)
            
        with open(rubric_path, "r", encoding="utf-8") as f:
            rubric = json.load(f)
            
        all_scores[domain] = []
        print(f"\n📁 Evaluating Domain: {domain.upper()}")
        
        # Limit samples for quick testing if needed
        samples = samples[:max_samples_per_domain]
        
        for idx, sample in enumerate(samples):
            task_id = sample.get("id", f"{domain}_{idx}")
            user_goal = sample.get("user_goal", "")
            target_ai = sample.get("primary_target", "AI")
            
            # Formulate the instruction for the provider being tested
            system_prompt = "You are an expert prompt engineer. Given the user's goal, write the perfect prompt for them."
            user_prompt = f"Goal: {user_goal}\nTarget AI: {target_ai}\nWrite the final prompt."
            
            # Generation
            start_t = time.time()
            generated_prompt = provider.generate(system_prompt, user_prompt)
            latency = time.time() - start_t
            
            system_metrics["total_latency_sec"] += latency
            system_metrics["total_samples"] += 1
            
            # Save Output separately
            output_file = os.path.join(OUTPUTS_DIR, f"{task_id}_{run_timestamp}.md")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(generated_prompt)
            
            # Evaluation
            print(f"  [>] Evaluating {task_id}... ", end="", flush=True)
            eval_result = evaluator.evaluate(generated_prompt, sample, rubric)
            eval_result["task_id"] = task_id
            eval_result["latency"] = latency
            eval_result["output_file"] = output_file
            
            all_scores[domain].append(eval_result)
            print(f"Score: {eval_result['final_score']}/100")
            
            # Respect rate limits for the judge
            time.sleep(2)
            
    # 3. Save Results
    system_metrics["end_time"] = time.time()
    
    with open(os.path.join(run_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
        
    with open(os.path.join(run_dir, "scores.json"), "w", encoding="utf-8") as f:
        json.dump(all_scores, f, indent=2)
        
    with open(os.path.join(run_dir, "system_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(system_metrics, f, indent=2)
        
    # 4. Generate Analytics Report
    report_path = os.path.join(run_dir, "report.md")
    generate_report(all_scores, config_data, system_metrics, report_path)
    
    print(f"\n✅ Experiment complete! Results saved to {run_dir}")

from prometheus.providers.local_unsloth import LocalUnslothProvider

if __name__ == "__main__":
    # Run the experiment with the LocalUnslothProvider
    target_provider = LocalUnslothProvider(model_name="unsloth/gemma-4-E4B-it", weights_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "model_weights"))
    run_experiment("gemma-4-E4B-it", target_provider, max_samples_per_domain=1)
