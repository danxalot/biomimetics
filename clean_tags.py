import os
import re

FILES_TO_CLEAN = [
    "docs/INTEGRATION_VERIFICATION.md",
    "docs/MIGRATION_EXECUTION_REPORT.md",
    "docs/GITHUB_MCP_SSE_DEPLOYMENT.md",
    "docs/DUAL_PROTOCOL_EMAIL_DAEMON.md",
    "docs/FIX_THE_BLEEDING_REPORT.md",
    "docs/swarm_integration_map.md"
]

TAG_CLEANUP_REGEX = r'(#(?:bios|pythia|context|source|arca)/[A-Za-z0-9_/-]+[:\.]?\s*)+$'

def clean_file_tags(fpath):
    if not os.path.exists(fpath):
        print(f"Skipping: {fpath} (Not found)")
        return
    
    print(f"Cleaning: {fpath}...")
    with open(fpath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        # Strip the trailing tags using the surgical regex
        cleaned_line = re.sub(TAG_CLEANUP_REGEX, '', line.rstrip('\n'))
        new_lines.append(cleaned_line + '\n')
    
    with open(fpath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"✅ Scrubbed {fpath}")

def main():
    print("="*60)
    print("  BiOS Tag Surgical Scrub Tool")
    print("="*60)
    for f in FILES_TO_CLEAN:
        clean_file_tags(f)
    print("\nScrub Complete.")

if __name__ == "__main__":
    main()
