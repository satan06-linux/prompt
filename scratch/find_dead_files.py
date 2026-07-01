import os

services_dir = "d:/Nexabuild/forge/services"
root_dir = "d:/Nexabuild/forge"
exclude_dirs = {"env", ".git", "__pycache__", ".pytest_cache", "node_modules", "unsloth_compiled_cache", "backups"}

all_service_files = [f for f in os.listdir(services_dir) if f.endswith(".py") and f != "__init__.py"]

all_python_files = []
for root, dirs, files in os.walk(root_dir):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for file in files:
        if file.endswith(".py"):
            all_python_files.append(os.path.join(root, file))

dead_files = []

for srv_file in all_service_files:
    mod_name = srv_file[:-3]
    is_imported = False
    
    for py_file in all_python_files:
        if os.path.abspath(py_file) == os.path.abspath(os.path.join(services_dir, srv_file)):
            continue
            
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()
            if f"services.{mod_name}" in content or f"from services import {mod_name}" in content or f"from {mod_name}" in content or f"import {mod_name}" in content:
                is_imported = True
                break
                
    if not is_imported:
        dead_files.append(srv_file)

with open("d:/Nexabuild/forge/scratch/dead_files.txt", "w") as f:
    for df in dead_files:
        f.write(df + "\n")

print(f"Found {len(dead_files)} dead files out of {len(all_service_files)} service files.")
