import os
import sys
import shutil
import glob
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from geometry_kernel.holistic_auditor import HolisticAuditor

INBOX_PATH = "shared_storage/concept_farm/inbox"
PROCESSING_PATH = "shared_storage/concept_farm/processing"
WORLD_MODEL_PATH = "shared_storage/world_model/analysis"
ARCHIVE_PATH = "archive/legacy_v1/garbage"

def ensure_dirs():
    os.makedirs(PROCESSING_PATH, exist_ok=True)
    os.makedirs(WORLD_MODEL_PATH, exist_ok=True)
    os.makedirs(ARCHIVE_PATH, exist_ok=True)

def main():
    ensure_dirs()
    print("Initializing Holistic Auditor (The Triad)...")
    auditor = HolisticAuditor()
    
    files = glob.glob(os.path.join(INBOX_PATH, "*"))
    print(f"Found {len(files)} files in Inbox.")
    
    for file_path in files:
        if os.path.isdir(file_path):
            continue
            
        filename = os.path.basename(file_path)
        print(f"\nProcessing: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            # Run the audit
            print("  Running Audit...", end="", flush=True)
            verdict = auditor.audit_proposal(content[:1000]) # Audit first 1000 chars aka 'Abstract'
            print(" Done.")
            print(f"  Verdict: {verdict}")
            
            # Simple parsing of the narrator's output
            if "APPROVE" in verdict:
                dest = os.path.join(WORLD_MODEL_PATH, filename)
                print(f"  -> Assimilating to World Model: {dest}")
                shutil.move(file_path, dest)
            elif "REJECT" in verdict:
                dest = os.path.join(PROCESSING_PATH, filename)
                print(f"  -> Rejecting to Processing: {dest}")
                shutil.move(file_path, dest)
            else:
                # Ambiguous
                dest = os.path.join(PROCESSING_PATH, filename)
                print(f"  -> Ambiguous verdict, moving to Processing: {dest}")
                shutil.move(file_path, dest)
                
        except Exception as e:
            print(f"  ERROR processing file: {e}")
            # Move to processing to unblock inbox
            dest = os.path.join(PROCESSING_PATH, filename)
            shutil.move(file_path, dest)

if __name__ == "__main__":
    main()
