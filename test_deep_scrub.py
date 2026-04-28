import re

def deep_scrub(text):
    # 1. Clean #[[...]] and #[[...]]/[[...]]
    text = re.sub(r'#\[\[.*?\]\](/\[\[.*?\]\])?', '', text)
    # 2. Clean trailing clusters of #tags that might be duplicates
    text = re.sub(r'(#[a-zA-Z0-9_/]+\s*){2,}', lambda m: ' '.join(sorted(set(m.group(0).split()))), text)
    # 3. Final cleanup of any lingering bracketed tags
    text = re.sub(r'#\[\[.*?\]\]', '', text)
    return text.strip()

sample = "Purpose: Verify all MCP endpoints #[[context]]/[[projects]] #[[bios]]/[[infrastructure]] #context #projects #context #legal"
print(f"Original: {sample}")
print(f"Scrubbed: {deep_scrub(sample)}")
