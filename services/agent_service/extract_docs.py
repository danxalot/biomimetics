#!/usr/bin/env python3
"""Extract documentation from checkpoint responses and save to files"""

import json
import re
from pathlib import Path

# Load checkpoint
with open('/home/ubuntu/mcp_storage/ARCA/checkpoints/comprehensive_analysis_overnight.json', 'r') as f:
    checkpoint = json.load(f)

output_dir = Path('/home/ubuntu/mcp_storage/ARCA/gemini_final')
output_dir.mkdir(parents=True, exist_ok=True)

print("="*60)
print("Extracting Documentation from Checkpoint")
print("="*60)

# Process each completed subtask
for idx, task in enumerate(checkpoint['state']['completed_subtasks'], 1):
    print(f"\n{idx}. Processing: {task['name']}")
    response = task['result']['response']
    
    # Check if this task generated documentation
    if 'file_write' in response.lower() or 'generate_' in task['name']:
        print(f"   Contains documentation content")
        
        # Try multiple extraction patterns
        patterns = [
            r'"content":\s*"(.*?)"(?:\s*}|,)',
            r'content["\s:=>]+"(.*?)"',
            r'# .*?\n(.*?)(?:\n\n|\Z)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.MULTILINE)
            if matches:
                content = matches[0] if isinstance(matches[0], str) else matches[0][0]
                
                # Determine filename based on task name
                if 'generate_01' in task['name']:
                    filename = '01_CURRENT_STATE_ASSESSMENT.md'
                elif 'generate_02' in task['name']:
                    filename = '02_DESIGN_EVOLUTION_HISTORY.md'
                elif 'generate_03' in task['name']:
                    filename = '03_TECHNICAL_SPECIFICATIONS.md'
                elif 'generate_04' in task['name']:
                    filename = '04_INTEGRATION_ROADMAP.md'
                elif 'generate_05_06_07' in task['name']:
                    # This task generated multiple files
                    filename = None  # Handle specially
                elif 'generate_00' in task['name']:
                    filename = '00_INDEX.md'
                else:
                    continue
                
                if filename:
                    # Save the content
                    output_path = output_dir / filename
                    with open(output_path, 'w') as f:
                        # Un-escape the content
                        content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\t', '\t')
                        f.write(content)
                    print(f"   ✅ Created: {filename} ({len(content)} bytes)")
                    break

# Also save the full responses as reference
print("\n" + "="*60)
print("Saving full responses for manual extraction if needed")
print("="*60)

for idx, task in enumerate(checkpoint['state']['completed_subtasks'], 1):
    response_file = output_dir / f"response_{idx}_{task['name']}.txt"
    with open(response_file, 'w') as f:
        f.write(f"Task: {task['name']}\n")
        f.write(f"Completed: {task['completed_at']}\n")
        f.write(f"Status: {task['result']['status']}\n")
        f.write(f"Actions: {task['result']['actions_taken']}\n")
        f.write(f"\n{'='*60}\n")
        f.write(f"RESPONSE:\n")
        f.write(f"{'='*60}\n\n")
        f.write(task['result']['response'])
    print(f"Saved full response: response_{idx}_{task['name']}.txt")

print("\n" + "="*60)
print(f"Output directory: {output_dir}")
print("="*60)
