import os
import argparse
from huggingface_hub import snapshot_download

def download_model(repo_id, destination):
    print(f"🚀 Downloading model weights for: {repo_id}")
    print(f"📂 Saving to: {destination}")
    print("⏳ This may take a few minutes depending on your internet connection...")
    
    # Download the repository, excluding large .git histories
    path = snapshot_download(
        repo_id=repo_id,
        local_dir=destination,
        local_dir_use_symlinks=False,  # Download actual files, not symlinks (crucial for Windows)
        ignore_patterns=["*.git*"]
    )
    
    print(f"✅ Download complete! Model successfully saved to {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download OMNICORE Models from HuggingFace")
    parser.add_argument(
        "--repo", 
        type=str, 
        default="unsloth/Phi-3-mini-4k-instruct", 
        help="The HuggingFace repository ID (e.g., unsloth/Phi-3-mini-4k-instruct)"
    )
    parser.add_argument(
        "--dest", 
        type=str, 
        default="OMNICORE/model_weights", 
        help="Local destination folder to save the weights"
    )
    
    args = parser.parse_args()
    
    # Ensure destination exists
    os.makedirs(args.dest, exist_ok=True)
    
    download_model(args.repo, args.dest)
