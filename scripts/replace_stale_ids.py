import os
import re

MAPPINGS = {
    # Biomimetic OS -> BiOS Tasks
    "3284d2d9fc7c811188deeeaba9c5f845": "3284d2d9fc7c811188deeeaba9c5f845",
    "3284d2d9-fc7c-8111-88de-eeaba9c5f845": "3284d2d9-fc7c-8111-88de-eeaba9c5f845",
    
    # CoPaw Approval -> Tool Guard
    "3284d2d9fc7c8113bfecca75f4235ece": "3284d2d9fc7c8113bfecca75f4235ece",
    "3284d2d9-fc7c-8113-bfee-cca75f4235ece": "3284d2d9-fc7c-8113-bfee-cca75f4235ece",
}

# 3284d2d9fc7c81bd9a91e865511e642f is used for both Life OS Triage and Tool Guard.
# I'll manually handle this depending on the line content.
# If the line contains "triage" (case insensitive), we map to BiOS Triage (3284d2d9fc7c81bd9a91e865511e642f)
# Otherwise, we assume Tool Guard (3284d2d9fc7c8113bfecca75f4235ece)

SHARED_STALE = "3284d2d9fc7c8113bfecca75f4235ece"
SHARED_STALE_HYPHEN = "3284d2d9-fc7c-8113-bfe-ecca75f4235ece"

TRIAGE_NEW = "3284d2d9fc7c81bd9a91e865511e642f"
TRIAGE_NEW_HYPHEN = "3284d2d9-fc7c-81bd-9a91-e865511e642f"

GUARD_NEW = "3284d2d9fc7c8113bfecca75f4235ece"
GUARD_NEW_HYPHEN = "3284d2d9-fc7c-8113-bfe-ecca75f4235ece"

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    original_content = content
    
    # Direct mappings
    for old, new in MAPPINGS.items():
        content = content.replace(old, new)
        
    # Handling shared stale ID by line
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if SHARED_STALE in line:
            if 'triage' in line.lower() or 'email' in line.lower() or 'webhook' in line.lower():
                line = line.replace(SHARED_STALE, TRIAGE_NEW)
            else:
                line = line.replace(SHARED_STALE, GUARD_NEW)
        if SHARED_STALE_HYPHEN in line:
            if 'triage' in line.lower() or 'email' in line.lower() or 'webhook' in line.lower():
                line = line.replace(SHARED_STALE_HYPHEN, TRIAGE_NEW_HYPHEN)
            else:
                line = line.replace(SHARED_STALE_HYPHEN, GUARD_NEW_HYPHEN)
        new_lines.append(line)
        
    content = '\n'.join(new_lines)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
        return True
    return False

def main():
    root_dir = '/Users/danexall/biomimetics'
    extensions = {'.py', '.js', '.json', '.toml', '.md', '.sh'}
    ignored_dirs = {'node_modules', '.git', '.gemini', '.pytest_cache', '__pycache__', 'obsidian_staging'}
    
    updated_count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude ignored directories
        dirnames[:] = [d for d in dirnames if d not in ignored_dirs and not d.endswith('.resolved')]
        
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                filepath = os.path.join(dirpath, filename)
                if process_file(filepath):
                    updated_count += 1
                    
    print(f"Total files updated: {updated_count}")

if __name__ == '__main__':
    main()
