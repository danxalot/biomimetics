#!/usr/bin/env python3
"""
Extract clean markdown files from response JSON files
"""

import json
import re
import os
from pathlib import Path

def extract_markdown_from_response(response_file):
    """Extract markdown content from response file"""
    with open(response_file, 'r') as f:
        content = f.read()
    
    extracted_files = []
    
    # Look for the pattern: "content": "markdown_text_here"
    # The content field contains the markdown with \n for newlines
    pattern = r'"path":\s*"([^"]+)",\s*"content":\s*"((?:[^"\\]|\\.)*)"'
    
    matches = re.finditer(pattern, content)
    
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
    source_dir = Path('/home/ubuntu/ARCA/gemini_final')
    output_dir = Path('/home/ubuntu/ARCA/gemini_final/extracted')
    
    # Create output directory
    output_dir.mkdir(exist_ok=True)
    
    # Process all response files
    response_files = sorted(source_dir.glob('response_*.txt'))
    
    print(f"Found {len(response_files)} response files to process\n")
    
    all_extracted = []
    for response_file in response_files:
        print(f"Processing: {response_file.name}")
        extracted = extract_markdown_from_response(response_file)
        
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
            print(f"  ⚠ No markdown content found in {response_file.name}")
    
    print(f"\n✅ Extraction complete!")
    print(f"Total files extracted: {len(all_extracted)}")
    print(f"Output directory: {output_dir}")
    
    if all_extracted:
        print(f"\nExtracted files:")
        for filename in sorted(all_extracted):
            file_path = output_dir / filename
            size = file_path.stat().st_size
            print(f"  - {filename} ({size:,} bytes)")

if __name__ == '__main__':
    main()
