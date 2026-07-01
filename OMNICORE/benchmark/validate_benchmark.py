"""
Nexafian AI Prompt Evaluation Framework - Benchmark Validator
=============================================================
Validates all dataset.json files across the benchmark suite for:
- JSON integrity & schema compliance
- Unique IDs and user_requests
- Valid enum values (difficulty, complexity, etc.)
- Evaluation weight summation (must equal 100)
- Distribution statistics reporting

Usage:
    python prometheus/benchmark/validate_benchmark.py
"""

import json
import os
import sys
from collections import Counter

# Force UTF-8 encoding for Windows terminal (prevents cp1252 emoji crashes)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BENCHMARK_DIR = os.path.dirname(os.path.abspath(__file__))

VALID_DIFFICULTIES = {"Easy", "Medium", "Hard", "Expert"}
VALID_COMPLEXITIES = {"Simple", "Intermediate", "Advanced", "Enterprise"}
VALID_EXPERTISE = {"Beginner", "Professional", "Senior", "Expert", "Research"}
VALID_OUTPUTS = {
    "markdown", "json", "xml", "code", "html", "yaml", "pdf",
    "diagram", "table", "image", "audio", "video", "text"
}

REQUIRED_FIELDS = [
    "id", "metadata", "category", "subcategory", "difficulty", "complexity",
    "expertise_level", "domain", "capability", "prompt_type", "user_request",
    "user_goal", "expected_output", "primary_target", "optimized_for",
    "compatible_models", "token_estimates", "expected_prompt_sections",
    "expected_prompt_characteristics", "evaluation_weights", "success_criteria",
    "common_failures", "reference_prompts", "results", "edge_cases", "tags"
]

REQUIRED_WEIGHT_KEYS = {"accuracy", "clarity", "structure", "constraints", "creativity"}

def validate_sample(sample, idx, domain, errors):
    """Validate a single benchmark sample."""
    prefix = f"[{domain}/{idx}] (ID: {sample.get('id', 'MISSING')})"

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in sample:
            errors.append(f"{prefix} Missing required field: '{field}'")
        elif sample[field] is None and field not in ("reference_prompts", "results"):
            errors.append(f"{prefix} Field '{field}' is None")

    # Check non-empty strings
    for str_field in ["id", "category", "subcategory", "user_request", "user_goal", "domain"]:
        val = sample.get(str_field, "")
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{prefix} Field '{str_field}' is empty or not a string")

    # Check enums
    if sample.get("difficulty") not in VALID_DIFFICULTIES:
        errors.append(f"{prefix} Invalid difficulty: '{sample.get('difficulty')}'")
    if sample.get("complexity") not in VALID_COMPLEXITIES:
        errors.append(f"{prefix} Invalid complexity: '{sample.get('complexity')}'")
    if sample.get("expertise_level") not in VALID_EXPERTISE:
        errors.append(f"{prefix} Invalid expertise_level: '{sample.get('expertise_level')}'")
    if sample.get("expected_output") not in VALID_OUTPUTS:
        errors.append(f"{prefix} Invalid expected_output: '{sample.get('expected_output')}'")

    # Check arrays are non-empty
    for arr_field in ["compatible_models", "expected_prompt_sections", "tags"]:
        val = sample.get(arr_field)
        if not isinstance(val, list) or len(val) == 0:
            errors.append(f"{prefix} Field '{arr_field}' is empty or not an array")

    # Check evaluation_weights sum to 100
    weights = sample.get("evaluation_weights", {})
    if isinstance(weights, dict):
        weight_sum = sum(weights.values())
        if weight_sum != 100:
            errors.append(f"{prefix} evaluation_weights sum to {weight_sum}, expected 100")
    else:
        errors.append(f"{prefix} evaluation_weights is not a dict")

    # Check metadata structure
    meta = sample.get("metadata", {})
    if isinstance(meta, dict):
        for mk in ["created_by", "created_at", "version", "generator_model", "reviewed"]:
            if mk not in meta:
                errors.append(f"{prefix} metadata missing key: '{mk}'")
    else:
        errors.append(f"{prefix} metadata is not a dict")

    # Check token_estimates structure
    tokens = sample.get("token_estimates", {})
    if isinstance(tokens, dict):
        for tk in ["estimated_prompt_size", "estimated_response_size", "estimated_context_tokens"]:
            if tk not in tokens:
                errors.append(f"{prefix} token_estimates missing key: '{tk}'")
    else:
        errors.append(f"{prefix} token_estimates is not a dict")

    # Check success_criteria structure
    sc = sample.get("success_criteria", {})
    if isinstance(sc, dict):
        for sk in ["excellent_characteristics", "acceptable_characteristics", "minimum_requirements"]:
            if sk not in sc:
                errors.append(f"{prefix} success_criteria missing key: '{sk}'")
    else:
        errors.append(f"{prefix} success_criteria is not a dict")


def validate_benchmark():
    """Run full validation across all domain folders."""
    print("=" * 70)
    print(" 🔍 NEXAFIAN BENCHMARK VALIDATOR")
    print("=" * 70)

    all_ids = []
    all_requests = []
    all_samples = []
    errors = []
    domain_counts = {}

    # Discover domain folders
    domains = sorted([
        d for d in os.listdir(BENCHMARK_DIR)
        if os.path.isdir(os.path.join(BENCHMARK_DIR, d)) and d != "__pycache__"
    ])

    if not domains:
        print("❌ No domain folders found!")
        return False

    print(f"\n📂 Found {len(domains)} domain folders: {', '.join(domains)}\n")

    for domain in domains:
        dataset_path = os.path.join(BENCHMARK_DIR, domain, "dataset.json")
        if not os.path.exists(dataset_path):
            errors.append(f"[{domain}] Missing dataset.json")
            continue

        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                samples = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"[{domain}] Invalid JSON in dataset.json: {e}")
            continue

        if not isinstance(samples, list):
            errors.append(f"[{domain}] dataset.json root is not an array")
            continue

        domain_counts[domain] = len(samples)
        print(f"  📁 {domain}: {len(samples)} samples")

        for idx, sample in enumerate(samples):
            validate_sample(sample, idx, domain, errors)
            all_ids.append(sample.get("id", f"MISSING-{domain}-{idx}"))
            all_requests.append(sample.get("user_request", ""))
            all_samples.append(sample)

    # Check for duplicate IDs
    id_counts = Counter(all_ids)
    for id_val, count in id_counts.items():
        if count > 1:
            errors.append(f"Duplicate ID found {count} times: '{id_val}'")

    # Check for duplicate user_requests
    req_counts = Counter(all_requests)
    for req, count in req_counts.items():
        if count > 1 and req:
            errors.append(f"Duplicate user_request found {count} times: '{req[:80]}...'")

    # Print distribution statistics
    print("\n" + "-" * 70)
    print(" 📊 DISTRIBUTION STATISTICS")
    print("-" * 70)

    if all_samples:
        for field_name in ["difficulty", "complexity", "expertise_level", "prompt_type", "primary_target"]:
            dist = Counter(s.get(field_name, "Unknown") for s in all_samples)
            print(f"\n  {field_name}:")
            for val, count in sorted(dist.items(), key=lambda x: -x[1]):
                pct = (count / len(all_samples)) * 100
                bar = "█" * int(pct / 2)
                print(f"    {val:30s} {count:4d} ({pct:5.1f}%) {bar}")

    # Report results
    print("\n" + "=" * 70)
    total = sum(domain_counts.values())
    if errors:
        print(f" ❌ VALIDATION FAILED: {len(errors)} errors found in {total} samples")
        print("=" * 70)
        for err in errors[:50]:  # Show first 50 errors
            print(f"  ⚠️ {err}")
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more errors")
        return False
    else:
        print(f" ✅ VALIDATION PASSED: {total} samples across {len(domains)} domains — ALL CLEAN")
        print("=" * 70)
        return True


if __name__ == "__main__":
    success = validate_benchmark()
    sys.exit(0 if success else 1)
