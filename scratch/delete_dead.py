import os

dead_files_txt = "d:/Nexabuild/forge/scratch/dead_files.txt"
services_dir = "d:/Nexabuild/forge/services"

if not os.path.exists(dead_files_txt):
    print("dead_files.txt not found!")
    exit(1)

with open(dead_files_txt, "r", encoding="utf-8") as f:
    files_to_delete = f.read().splitlines()

deleted_count = 0
for file in files_to_delete:
    if not file.strip():
        continue
    filepath = os.path.join(services_dir, file)
    if os.path.exists(filepath):
        os.remove(filepath)
        deleted_count += 1
    else:
        print(f"File not found: {filepath}")

print(f"Successfully deleted {deleted_count} files from the services directory.")
