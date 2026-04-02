import json
import os

filepath = "/Users/danexall/.copaw/venv/lib/python3.12/site-packages/agentscope/model/_openai_model.py"
if not os.path.exists(filepath):
    print(f"FATAL ERROR: {filepath} not found. Pip install failed.")
    exit(1)

with open(filepath, "r") as f:
    content = f.read()

sanitizer_code = """
import json

def _sanitize_tool_schema(tools):
    if not tools: return tools
    tools_copy = json.loads(json.dumps(tools))
    def remove_refs(obj):
        if isinstance(obj, dict):
            if "items" in obj and isinstance(obj["items"], dict) and "$ref" in obj["items"]:
                del obj["items"]["$ref"]
                obj["items"]["type"] = "object"
            for k, v in list(obj.items()):
                if k == "$ref": del obj[k]
                else: remove_refs(v)
        elif isinstance(obj, list):
            for item in obj: remove_refs(item)
    remove_refs(tools_copy)
    return tools_copy
"""
if "_sanitize_tool_schema" not in content:
    content = content.replace("import time", "import time\n" + sanitizer_code)
    
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if "response = await self.client.chat.completions.create(**kwargs)" in line and "if" not in line:
            indent = line.split("response")[0]
            new_lines.append(indent + 'if "tools" in kwargs:')
            new_lines.append(indent + '    kwargs["tools"] = _sanitize_tool_schema(kwargs["tools"])')
            new_lines.append(line)
        else:
            new_lines.append(line)

    with open(filepath, "w") as f:
        f.write('\n'.join(new_lines))
    print("✅ AgentScope successfully patched for Gemini.")
else:
    print("✅ AgentScope was already patched.")
