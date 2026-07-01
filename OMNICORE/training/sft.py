import os
# Disable torch.compile which is not supported on Windows
os.environ["TORCH_COMPILE_DISABLE"] = "1" 
# Maximum memory fragmentation reduction
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

from unsloth import FastLanguageModel


import sys
import json
import torch
import builtins
import pathlib

# Global Windows UTF-8 Monkeypatch to prevent TRL / Pathlib read_text crashes
real_open = builtins.open
def utf8_open(*args, **kwargs):
    # Detect if opened in binary mode
    mode = kwargs.get('mode', '')
    if len(args) > 1:
        mode = args[1]
    is_binary = 'b' in mode if isinstance(mode, str) else False
    
    if not is_binary and 'encoding' not in kwargs:
        kwargs['encoding'] = 'utf-8'
    return real_open(*args, **kwargs)
builtins.open = utf8_open

real_read_text = pathlib.Path.read_text
def utf8_read_text(self, encoding=None, errors=None):
    return real_read_text(self, encoding=encoding or 'utf-8', errors=errors)
pathlib.Path.read_text = utf8_read_text

real_path_open = pathlib.Path.open
def utf8_path_open(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
    if 'r' in mode and 'b' not in mode and encoding is None:
        encoding = 'utf-8'
    return real_path_open(self, mode=mode, buffering=buffering, encoding=encoding, errors=errors, newline=newline)
pathlib.Path.open = utf8_path_open

# Force UTF-8 encoding for Windows terminal prints
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Inject FP8BackendType into builtins to prevent Unsloth dynamically compiled scoping NameErrors
try:
    from accelerate.utils.dataclasses import FP8BackendType
    builtins.FP8BackendType = FP8BackendType
except ImportError:
    try:
        from accelerate.utils import FP8BackendType
        builtins.FP8BackendType = FP8BackendType
    except ImportError:
        pass


from datasets import Dataset
from trl import SFTTrainer
from transformers import TrainingArguments

if __name__ == '__main__':
    # Load base model
    print("🔥 Loading Qwen2.5 3B base model in 4-bit...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/Qwen2.5-3B-Instruct",
        max_seq_length=512, # Reduced from 2048 to fit 6GB VRAM
        dtype=torch.float16,
        load_in_4bit=True,
        device_map="cuda", # Force it onto the GPU to stop the CPU offload crash
    )

    # LoRA config
    model = FastLanguageModel.get_peft_model(
        model,
        r=8, # Reduced from 16
        target_modules=["q_proj", "v_proj"], # Reduced from 7 modules to save VRAM on backward pass
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth", # Use Unsloth's ultra-efficient checkpointing instead of standard True

        random_state=42,
    )

    # Load dataset (Strictly isolated from benchmark data)
    dataset_path = os.path.join(os.path.dirname(__file__), "synthetic_training_dataset.json")
    if not os.path.exists(dataset_path):
        # Fallback to older training dataset if synthetic one hasn't been generated yet
        dataset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prometheus_dataset_v1.json")

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    def format_example(example):
        # If the dataset is in the prompt evaluation style, format it appropriately
        if "instruction" in example:
            return {
                "text": f"""<|system|>
You are Prometheus AI by Nexafian acting as a fair evaluator.
<|end|>
<|user|>
Evaluate: {example['instruction']}
Rubric: {example['rubric']}
Response: {example['response']}
Reference: {example['reference_answer']}
<|end|>
<|assistant|>
[Feedback] {example['feedback']}
[Score] {example['score']}
<|end|>"""
            }
        
        # Otherwise, use the MCQ prompt builder style
        mcq_text = "\n".join([
            f"Q: {q['question']}\nA: {q['answer']}"
            for q in example.get("mcqs", [])
        ])
        return {
            "text": f"""<|system|>
You are Prometheus AI by Nexafian. You are a specialized 
prompt engineering model. Given a user concept and their 
MCQ answers, generate a precise, professional, ready-to-use 
AI prompt. Output only the final prompt, nothing else.
<|end|>
<|user|>
Concept: {example.get('input', '')}
Category: {example.get('category', '')}
User answers:
{mcq_text}
<|end|>
<|assistant|>
{example.get('output', '')}
<|end|>"""
        }

    formatted = [format_example(e) for e in data]
    dataset = Dataset.from_list(formatted)

    output_dir = os.path.join(os.path.dirname(__file__), "model_weights")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=512, # Reduced from 2048
        dataset_num_proc=2,
        args=TrainingArguments(
            per_device_train_batch_size=1, # Reduced from 2
            gradient_accumulation_steps=8, # Increased from 4 to keep effective batch size = 8
            warmup_steps=20,
            num_train_epochs=8,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=10,
            optim="paged_adamw_8bit", # Changed to Paged AdamW to allow optimizer CPU offloading
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            output_dir=output_dir,
            save_strategy="no", # Disabled to prevent pickling error on SFTConfig
            report_to="none",
        ),
    )

    print("Training Prometheus-1 (Phi-3-mini)... this will take 2-4 hours on RTX 4050")
    trainer.train()

    # CRITICAL FIX FOR WINDOWS BSOD / CRASHING
    # The laptop crashes here because saving the model spikes the System RAM when the Optimizer is still loaded.
    # We must explicitly delete the trainer and clear the GPU/RAM cache before saving!
    print("🧹 Clearing Optimizer Memory from System RAM to prevent Windows Crash...")
    import gc
    del trainer
    torch.cuda.empty_cache()
    gc.collect()

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"🎉 Prometheus-1 saved to: {output_dir}")
