import re
text = "Purpose: Verify all MCP endpoints #[[context/projects]] #[[bios/infrastructure]]"
scrubbed = re.sub(r'#\[\[(.*?)\]\]', r'#\1', text)
print(f"Original: {text}")
print(f"Scrubbed: {scrubbed}")
