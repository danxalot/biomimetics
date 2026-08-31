import json
import sys

try:
    with open('gemma_design_response.json', 'r') as f:
        data = json.load(f)
    
    parts = data['candidates'][0]['content']['parts']
    
    # Find the part that is NOT a thought (usually index 1 if thought is index 0)
    # Or just print everything that has text.
    
    with open('gemma_design.md', 'w') as out:
        for part in parts:
            if 'text' in part:
                if part.get('thought'):
                    out.write("<!-- THOUGHTS:\n" + part['text'] + "\n-->\n\n")
                else:
                    out.write(part['text'] + "\n")
    print("✅ Design text extracted to gemma_design.md")
except Exception as e:
    print(f"❌ Error: {e}")
