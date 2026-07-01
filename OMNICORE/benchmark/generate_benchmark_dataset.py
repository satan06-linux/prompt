"""
Nexafian AI Prompt Evaluation Framework - Benchmark Dataset Generator
=====================================================================
Phase 1: Generates 100 high-quality evaluation samples across 10 domains
using Google Gemini 2.5 Flash via OpenRouter.

Usage:
    python prometheus/benchmark/generate_benchmark_dataset.py
"""

import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone

# Force UTF-8 encoding for Windows terminal (prevents cp1252 emoji crashes)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Append project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ============ CONFIGURATION ============

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {config.OPEN_ROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://forgeprompt.com",
    "X-Title": "Nexafian Benchmark Generator"
}
MODEL = "google/gemini-2.5-flash"
BENCHMARK_DIR = os.path.join(os.path.dirname(__file__))
CHECKPOINT_INTERVAL = 10

# ============ DOMAIN DEFINITIONS ============

DOMAINS = {
    "programming": {
        "subcategories": [
            "Backend API Development", "Frontend Frameworks", "Asynchronous Concurrency",
            "Database Architecture", "Microservices", "DevOps & CI/CD", "Cloud Computing",
            "Cybersecurity", "Mobile App Development", "System Design",
            "Algorithm Optimization", "Testing & QA", "Web Scraping", "CLI Tools",
            "Package Development", "GraphQL APIs", "WebSocket Real-time Systems",
            "Serverless Functions", "Code Refactoring", "Legacy Migration"
        ],
        "capabilities": ["Code Generation", "Debugging", "Code Review", "Architecture Design", "Optimization"],
    },
    "business": {
        "subcategories": [
            "Startup Strategy", "Marketing Campaigns", "Sales Funnels", "Brand Identity",
            "HR & Recruitment", "Customer Support Workflows", "Supply Chain Optimization",
            "Competitive Analysis", "Product Launch", "Business Model Canvas",
            "Pitch Deck Creation", "Market Research", "Partnership Strategy",
            "Pricing Strategy", "Growth Hacking", "Customer Retention",
            "OKR Planning", "Investor Relations", "Crisis Management", "Franchise Development"
        ],
        "capabilities": ["Planning", "Analysis", "Strategy", "Communication", "Optimization"],
    },
    "research": {
        "subcategories": [
            "Literature Review", "Hypothesis Formulation", "Experimental Design",
            "Data Analysis", "Academic Paper Writing", "Grant Proposal",
            "Peer Review Response", "Systematic Review", "Meta-Analysis",
            "Research Methodology", "Survey Design", "Statistical Modeling",
            "Citation Analysis", "Thesis Structure", "Conference Abstract",
            "Lab Protocol", "Ethical Review", "Reproducibility Audit",
            "Cross-disciplinary Synthesis", "Research Gap Identification"
        ],
        "capabilities": ["Reasoning", "Summarization", "Analysis", "Writing", "Planning"],
    },
    "healthcare": {
        "subcategories": [
            "Clinical Decision Support", "Patient Communication", "Drug Interaction Analysis",
            "Medical Report Summarization", "Telemedicine Workflow", "Health Education",
            "EHR Data Extraction", "Diagnostic Reasoning", "Treatment Protocol",
            "Mental Health Assessment", "Pharmacy Automation", "Epidemiology Modeling",
            "Clinical Trial Design", "Nursing Care Plans", "Radiology Report Generation",
            "Rehabilitation Planning", "Nutritional Assessment", "Surgery Pre-op Checklist",
            "Chronic Disease Management", "Public Health Campaign"
        ],
        "capabilities": ["Reasoning", "Summarization", "Planning", "Analysis", "Communication"],
    },
    "education": {
        "subcategories": [
            "Curriculum Design", "Lesson Planning", "Student Assessment",
            "E-Learning Content", "Tutoring Prompts", "Gamified Learning",
            "Special Education Adaptation", "STEM Activities", "Language Teaching",
            "Rubric Creation", "Parent Communication", "Professional Development",
            "Exam Question Generation", "Learning Objective Writing",
            "Classroom Management", "Differentiated Instruction", "Project-Based Learning",
            "Student Feedback", "Online Course Structure", "Academic Advising"
        ],
        "capabilities": ["Content Generation", "Planning", "Assessment", "Communication", "Design"],
    },
    "creative": {
        "subcategories": [
            "Short Story Writing", "Blog Post Creation", "Social Media Content",
            "Poetry Composition", "Screenwriting", "Journalism Article",
            "Video Script", "Podcast Outline", "Newsletter Design",
            "Brand Copywriting", "Game Narrative", "World Building",
            "Character Development", "Song Lyrics", "Advertising Copy",
            "Book Synopsis", "Creative Non-Fiction", "Satire & Comedy",
            "Translation & Localization", "SEO Content Strategy"
        ],
        "capabilities": ["Creative Writing", "Storytelling", "Content Generation", "Translation", "Design"],
    },
    "engineering": {
        "subcategories": [
            "Mechanical Design Specs", "Civil Structure Analysis", "Electrical Circuit Design",
            "Robotics Control Systems", "IoT Device Architecture", "Manufacturing Process",
            "CAD Model Instructions", "Material Selection", "Safety Analysis",
            "Environmental Impact Assessment", "Thermodynamics Modeling",
            "Fluid Dynamics Simulation", "Quality Control Protocol",
            "Maintenance Schedule", "Energy Efficiency Audit", "3D Printing Specs",
            "Embedded Systems", "Signal Processing", "Automation Workflow",
            "Supply Chain Engineering"
        ],
        "capabilities": ["Design", "Analysis", "Optimization", "Planning", "Simulation"],
    },
    "design": {
        "subcategories": [
            "UI Wireframe Specification", "UX Research Plan", "Logo Design Brief",
            "Interior Space Layout", "Product Industrial Design", "Fashion Collection Brief",
            "Architecture Floor Plan", "Graphic Design System", "Icon Set Design",
            "Mobile App UI Kit", "Dashboard Layout", "Packaging Design",
            "Typography System", "Color Palette Generation", "Landing Page Design",
            "Portfolio Website", "Design System Documentation", "Accessibility Audit",
            "Motion Design Storyboard", "Brand Guidelines"
        ],
        "capabilities": ["Design", "Image Generation", "Planning", "Analysis", "Communication"],
    },
    "ai_ml": {
        "subcategories": [
            "ML Pipeline Design", "Neural Network Architecture", "Prompt Engineering",
            "AI Agent Workflow", "Multi-Agent System", "RAG Pipeline",
            "Fine-Tuning Strategy", "Dataset Curation", "Model Evaluation",
            "MLOps Deployment", "Computer Vision Pipeline", "NLP Text Classification",
            "Recommendation System", "Anomaly Detection", "Time Series Forecasting",
            "Reinforcement Learning", "Transfer Learning", "AutoML Configuration",
            "LLM System Prompt", "AI Safety & Alignment"
        ],
        "capabilities": ["Code Generation", "Architecture Design", "Reasoning", "Optimization", "Planning"],
    },
    "finance": {
        "subcategories": [
            "Financial Modeling", "Investment Portfolio Analysis", "Tax Strategy",
            "Cryptocurrency Analysis", "Stock Market Prediction", "Risk Assessment",
            "Budgeting & Forecasting", "Audit Trail Design", "Compliance Reporting",
            "Insurance Underwriting", "Loan Assessment", "Fintech App Specification",
            "Trading Bot Strategy", "Revenue Projection", "Cost Optimization",
            "Mergers & Acquisitions", "Real Estate Valuation", "Accounting Automation",
            "Payment Gateway Integration", "Financial Dashboard Design"
        ],
        "capabilities": ["Analysis", "Planning", "Code Generation", "Reasoning", "Optimization"],
    },
}

# Difficulty distribution: 20% Easy, 30% Medium, 30% Hard, 20% Expert
DIFFICULTIES = ["Easy"] * 2 + ["Medium"] * 3 + ["Hard"] * 3 + ["Expert"] * 2

COMPLEXITIES = ["Simple", "Intermediate", "Advanced", "Enterprise"]

EXPERTISE_LEVELS = ["Beginner", "Professional", "Senior", "Expert", "Research"]

PROMPT_TYPES = [
    "Basic Prompt", "Advanced Prompt", "Expert Prompt", "System Prompt",
    "Agent Prompt", "Multi-Agent Prompt", "JSON Prompt", "XML Prompt",
    "Markdown Prompt", "Chain-of-Thought Prompt", "Role Prompt", "Persona Prompt",
    "Workflow Prompt", "Prompt Template", "Few-Shot Prompt", "Zero-Shot Prompt",
    "Structured Prompt", "Multi-Step Prompt"
]

TARGET_AIS = [
    "ChatGPT", "Claude", "Gemini", "Grok", "Cursor", "GitHub Copilot",
    "Stable Diffusion", "Flux", "Midjourney", "GPT Image", "Veo", "Kling",
    "Hailuo", "ComfyUI", "Blender AI", "ElevenLabs", "Suno", "NotebookLM"
]

EXPECTED_OUTPUTS = [
    "markdown", "json", "xml", "code", "html", "yaml", "pdf",
    "diagram", "table", "image", "audio", "video", "text"
]

EXPECTED_PROMPT_SECTIONS = [
    "Role", "Objective", "Context", "Requirements", "Constraints",
    "Input", "Output", "Examples", "Edge Cases", "Success Criteria"
]


# ============ API HELPER ============

def call_openrouter(system_prompt, user_prompt, max_tokens=4000, temperature=0.8):
    """Call OpenRouter API with retry logic."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    for attempt in range(5):
        try:
            response = httpx.post(OPENROUTER_URL, headers=HEADERS, json=payload, timeout=120.0)
            if response.status_code == 200:
                res_data = response.json()
                return res_data["choices"][0]["message"]["content"].strip()
            elif response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  ⚠️ Rate limited (429). Sleeping {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ⚠️ OpenRouter error {response.status_code}: {response.text[:200]}. Retrying...")
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ Request error: {e}. Retrying...")
            time.sleep(3)
    return None


def extract_json_from_response(text):
    """Extract JSON array or object from LLM response that may contain markdown fences."""
    if not text:
        return None
    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array or object
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        return None


# ============ GENERATION SYSTEM PROMPT ============

SYSTEM_PROMPT = """You are the world's best AI Evaluation Dataset Engineer.

You generate benchmark evaluation samples for testing prompt-generation systems.

Each sample tests whether an AI can generate a HIGH-QUALITY prompt for a given user request.

You MUST output a valid JSON array. Each item MUST follow this EXACT schema:

{
  "subcategory": "<specific subcategory>",
  "difficulty": "<Easy|Medium|Hard|Expert>",
  "complexity": "<Simple|Intermediate|Advanced|Enterprise>",
  "expertise_level": "<Beginner|Professional|Senior|Expert|Research>",
  "domain": "<specific domain name>",
  "capability": "<what AI capability is needed>",
  "prompt_type": "<type of prompt being generated>",
  "user_request": "<realistic user request - what a real person would type>",
  "user_goal": "<what the user actually wants to achieve>",
  "expected_output": "<markdown|json|xml|code|html|yaml|text|image|audio|video|diagram|table>",
  "primary_target": "<primary AI tool>",
  "optimized_for": "<which model it's optimized for>",
  "compatible_models": ["<list of compatible AI models>"],
  "token_estimates": {
    "estimated_prompt_size": <number>,
    "estimated_response_size": <number>,
    "estimated_context_tokens": <number>
  },
  "expected_prompt_sections": ["Role", "Objective", "Context", "Requirements", "Constraints", "Input", "Output", "Examples", "Edge Cases", "Success Criteria"],
  "expected_prompt_characteristics": ["<list of 2-4 key characteristics>"],
  "evaluation_weights": {
    "accuracy": <0-100>,
    "clarity": <0-100>,
    "structure": <0-100>,
    "constraints": <0-100>,
    "creativity": <0-100>
  },
  "success_criteria": {
    "excellent_characteristics": ["<list>"],
    "acceptable_characteristics": ["<list>"],
    "minimum_requirements": ["<list>"]
  },
  "common_failures": ["<list of 2-4 common mistakes>"],
  "edge_cases": ["<list of 1-3 edge cases>"],
  "tags": ["<relevant tags>"]
}

CRITICAL RULES:
1. evaluation_weights values MUST sum to exactly 100.
2. Every user_request must be UNIQUE and REALISTIC (what a real human would type).
3. Mix difficulties: some Easy (simple tasks), some Expert (enterprise-scale complex tasks).
4. Vary prompt_type across: System Prompt, Agent Prompt, JSON Prompt, Few-Shot Prompt, etc.
5. Vary primary_target across: ChatGPT, Claude, Gemini, Cursor, Midjourney, Suno, ElevenLabs, etc.
6. Output ONLY valid JSON. No explanations, no markdown fences, no extra text.
"""


# ============ MAIN GENERATOR ============

def generate_domain_samples(domain_name, domain_config, count=10):
    """Generate benchmark samples for a single domain."""
    subcategories = domain_config["subcategories"]
    capabilities = domain_config["capabilities"]

    user_prompt = f"""Generate exactly {count} unique, diverse, high-quality benchmark evaluation samples for the domain: **{domain_name.upper()}**

Available subcategories to choose from (use a good mix):
{json.dumps(subcategories, indent=2)}

Available capabilities to assign:
{json.dumps(capabilities, indent=2)}

Available prompt types (use diverse mix):
{json.dumps(PROMPT_TYPES[:10], indent=2)}

Available target AIs (use diverse mix):
{json.dumps(TARGET_AIS, indent=2)}

REQUIREMENTS:
- Generate EXACTLY {count} items in a JSON array.
- Every user_request must sound like a REAL person typing naturally.
- Mix difficulties: ~2 Easy, ~3 Medium, ~3 Hard, ~2 Expert.
- Mix complexity: Simple, Intermediate, Advanced, Enterprise.
- evaluation_weights MUST sum to exactly 100 for each item.
- Each item must be completely unique in user_request.
- Output ONLY the JSON array. No other text."""

    print(f"\n🔄 Generating {count} samples for [{domain_name}]...")
    raw = call_openrouter(SYSTEM_PROMPT, user_prompt, max_tokens=8000, temperature=0.85)

    if not raw:
        print(f"  ❌ Failed to get response for {domain_name}")
        return []

    items = extract_json_from_response(raw)

    if not items or not isinstance(items, list):
        print(f"  ❌ Failed to parse JSON for {domain_name}")
        print(f"  Raw response (first 500 chars): {raw[:500]}")
        return []

    # Post-process: add IDs, metadata, missing fields
    processed = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        # Build hierarchical ID
        subcat_slug = item.get("subcategory", "general").replace(" ", "-").upper()[:20]
        item_id = f"FP-{domain_name.upper()[:4]}-{subcat_slug}-{str(i+1).zfill(4)}"

        sample = {
            "id": item_id,
            "metadata": {
                "created_by": "generator",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
                "generator_model": "Gemini 2.5 Flash",
                "reviewed": False
            },
            "category": domain_name.replace("_", " ").title(),
            "subcategory": item.get("subcategory", "General"),
            "difficulty": item.get("difficulty", "Medium"),
            "complexity": item.get("complexity", "Intermediate"),
            "expertise_level": item.get("expertise_level", "Professional"),
            "domain": item.get("domain", domain_name.title()),
            "capability": item.get("capability", "Reasoning"),
            "prompt_type": item.get("prompt_type", "Basic Prompt"),
            "user_request": item.get("user_request", ""),
            "user_goal": item.get("user_goal", ""),
            "expected_output": item.get("expected_output", "text"),
            "primary_target": item.get("primary_target", "ChatGPT"),
            "optimized_for": item.get("optimized_for", "Gemma"),
            "compatible_models": item.get("compatible_models", ["Gemma", "GPT", "Claude"]),
            "token_estimates": item.get("token_estimates", {
                "estimated_prompt_size": 200,
                "estimated_response_size": 500,
                "estimated_context_tokens": 800
            }),
            "expected_prompt_sections": item.get("expected_prompt_sections", EXPECTED_PROMPT_SECTIONS),
            "expected_prompt_characteristics": item.get("expected_prompt_characteristics", []),
            "evaluation_weights": item.get("evaluation_weights", {
                "accuracy": 25, "clarity": 20, "structure": 20, "constraints": 20, "creativity": 15
            }),
            "success_criteria": item.get("success_criteria", {
                "excellent_characteristics": [],
                "acceptable_characteristics": [],
                "minimum_requirements": []
            }),
            "common_failures": item.get("common_failures", []),
            "reference_prompts": {
                "human": None, "gemma": None, "qwen": None,
                "phi": None, "gpt": None, "claude": None
            },
            "results": {},
            "edge_cases": item.get("edge_cases", []),
            "tags": item.get("tags", [])
        }

        # Validate evaluation_weights sum
        weights = sample["evaluation_weights"]
        weight_sum = sum(weights.values())
        if weight_sum != 100:
            # Normalize weights to sum to 100
            if weight_sum > 0:
                factor = 100.0 / weight_sum
                for k in weights:
                    weights[k] = round(weights[k] * factor)
                # Fix rounding errors
                diff = 100 - sum(weights.values())
                if diff != 0:
                    first_key = list(weights.keys())[0]
                    weights[first_key] += diff

        processed.append(sample)

    print(f"  ✅ Successfully generated {len(processed)} samples for [{domain_name}]")
    return processed


def save_domain_dataset(domain_name, samples):
    """Save samples to the domain's dataset.json file."""
    domain_dir = os.path.join(BENCHMARK_DIR, domain_name)
    os.makedirs(domain_dir, exist_ok=True)
    dataset_path = os.path.join(domain_dir, "dataset.json")

    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    print(f"  💾 Saved {len(samples)} samples to {dataset_path}")


def save_domain_statistics(domain_name, samples):
    """Generate and save statistics for a domain."""
    domain_dir = os.path.join(BENCHMARK_DIR, domain_name)
    os.makedirs(domain_dir, exist_ok=True)

    stats = {
        "total_samples": len(samples),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "difficulty_distribution": {},
        "complexity_distribution": {},
        "prompt_type_distribution": {},
        "primary_target_distribution": {},
        "capability_distribution": {}
    }

    for sample in samples:
        for key, stat_key in [
            ("difficulty", "difficulty_distribution"),
            ("complexity", "complexity_distribution"),
            ("prompt_type", "prompt_type_distribution"),
            ("primary_target", "primary_target_distribution"),
            ("capability", "capability_distribution")
        ]:
            val = sample.get(key, "Unknown")
            stats[stat_key][val] = stats[stat_key].get(val, 0) + 1

    stats_path = os.path.join(domain_dir, "statistics.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"  📊 Saved statistics to {stats_path}")


# ============ ENTRY POINT ============

if __name__ == "__main__":
    if not config.OPEN_ROUTER_API_KEY:
        print("❌ ERROR: OPEN_ROUTER_API_KEY not found in .env file!")
        sys.exit(1)

    print("=" * 70)
    print(" 🧠 NEXAFIAN AI PROMPT EVALUATION FRAMEWORK")
    print(" 📦 Phase 1: Generating 100 Benchmark Samples (10 domains × 10 each)")
    print("=" * 70)

    total_generated = 0
    all_ids = set()

    for domain_name, domain_config in DOMAINS.items():
        samples = generate_domain_samples(domain_name, domain_config, count=10)

        if samples:
            # Deduplicate IDs
            for sample in samples:
                while sample["id"] in all_ids:
                    sample["id"] += "-DUP"
                all_ids.add(sample["id"])

            save_domain_dataset(domain_name, samples)
            save_domain_statistics(domain_name, samples)
            total_generated += len(samples)

        # Brief pause between domains to avoid rate limits
        time.sleep(2)

    print("\n" + "=" * 70)
    print(f" ✅ Phase 1 Complete: {total_generated} total samples generated across {len(DOMAINS)} domains")
    print("=" * 70)
