#!/usr/bin/env python3
"""
Extract clean markdown files from checkpoint JSON
"""

import json
import re
from pathlib import Path

def extract_markdown_from_response(response_text):
    """Extract markdown content from a response string"""
    extracted_files = []
    
    # Look for JSON tool calls with file_write
    # Pattern: {"tool_name": "file_write", "arguments": {"path": "...", "content": "..."}}
    pattern = r'\{"tool_name":\s*"file_write",\s*"arguments":\s*\{"path":\s*"([^"]+)",\s*"content":\s*"((?:[^"\\]|\\.)*?)"\}\}'
    
    matches = re.finditer(pattern, response_text, re.DOTALL)
    
    for match in matches:
        file_path = match.group(1)
        markdown_content = match.group(2)
        
        # Unescape the content
        markdown_content = markdown_content.replace('\\n', '\n')
        markdown_content = markdown_content.replace('\\"', '"')
        markdown_content = markdown_content.replace('\\t', '\t')
        markdown_content = markdown_content.replace('\\\\', '\\')
        
        extracted_files.append({
            'path': file_path,
            'content': markdown_content
        })
    
    return extracted_files

def main():
    checkpoint_path = Path('/home/ubuntu/mcp_storage/ARCA/checkpoints/comprehensive_analysis_overnight.json')
    output_dir = Path('/home/ubuntu/ARCA/gemini_final/extracted')
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    # Load checkpoint
    print(f"Loading checkpoint: {checkpoint_path}")
    with open(checkpoint_path, 'r') as f:
        checkpoint = json.load(f)
    
    # Extract from each completed subtask
    completed = checkpoint['state']['completed_subtasks']
    print(f"Found {len(completed)} completed subtasks\n")
    
    all_extracted = []
    for subtask in completed:
        task_name = subtask['name']
        response = subtask['result']['response']
        
        print(f"Processing: {task_name}")
        extracted = extract_markdown_from_response(response)
        
        if extracted:
            for item in extracted:
                # Get just the filename from the path
                filename = Path(item['path']).name
                output_path = output_dir / filename
                
                # Write the clean markdown
                with open(output_path, 'w') as f:
                    f.write(item['content'])
                
                file_size = len(item['content'])
                print(f"  ✓ Extracted: {filename} ({file_size:,} chars)")
                all_extracted.append(filename)
        else:
            print(f"  ⚠ No markdown files in {task_name}")
    
    print(f"\n✅ Extraction complete!")
    print(f"Total files extracted: {len(all_extracted)}")
    print(f"Output directory: {output_dir}")
    
    if all_extracted:
        print(f"\nExtracted markdown files:")
        for filename in sorted(set(all_extracted)):
            file_path = output_dir / filename
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"  - {filename} ({size:,} bytes)")

if __name__ == '__main__':
    main()
