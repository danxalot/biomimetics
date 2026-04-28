import re
text = "endpoints /[[projects]] /[[infrastructure]] #[[context]]/[[projects]] #context"
# Pattern to catch #[[...]] paths AND homeless /[[...]] paths
pattern = r'([#/](\[\[.*?\]\]/?)+)'
scrubbed = re.sub(pattern, '', text)
print(f"Original: {text}")
print(f"Scrubbed: {scrubbed}")
