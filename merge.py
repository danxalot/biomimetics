import re

with open("jarvis_daemon_head.py", "r") as f:
    head_code = f.read()

with open("scripts/copaw/jarvis_daemon.py", "r") as f:
    current_code = f.read()

# 1. From head_code, extract from line 47 (OPENCODE_TOKEN_PATH) up to the end of handle_tool_call (line 691)
# we can just find 'OPENCODE_TOKEN_PATH' and the end of 'handle_tool_call'
start_marker = "OPENCODE_TOKEN_PATH ="
end_marker = "class AudioLoop:"

start_idx = head_code.find(start_marker)
end_idx = head_code.find(end_marker)

middle_block = head_code[start_idx:end_idx]

# Remove the old MODEL and CONFIG definitions from middle_block if they exist
middle_block = re.sub(r'MODEL = ".*?"\nCONFIG = \{.*?\}\n', '', middle_block, flags=re.DOTALL)
middle_block = re.sub(r'client = genai\.Client\(.*?\)\n', '', middle_block)

# 2. Append the requested Model Configuration
new_config = """
# --- Model Configuration ---
# Reverted to the correct, working 2.5 native audio preview model
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025" 

CONFIG = {
    "system_instruction": SYSTEM_PROMPT,
    "response_modalities": ["AUDIO"],
    "tools": [
        {
            "function_declarations": [
                query_memory_tool,
                save_memory_tool,
                save_to_notion_tool,
                execute_heavy_reasoning_tool,
                preserve_session_context_tool,
                execute_computer_action_tool,
                engage_all_systems_tool,
                trigger_pm_agent_tool,
                contact_pythia_tool,
            ]
        }
    ],
}

# Ensure the client is pointed at v1beta
client = genai.Client(api_key=API_KEY, http_options={"api_version": "v1beta"})

"""

# 3. Find where to insert in current_code
# current_code has "# ... [Keep all your existing OPENCODE and VISION URL constants here exactly as they were] ..."
insert_marker_start = current_code.find("# ... [Keep all your")
insert_marker_end = current_code.find("class AudioLoop:")

if insert_marker_start != -1 and insert_marker_end != -1:
    final_code = current_code[:insert_marker_start] + middle_block + new_config + current_code[insert_marker_end:]
    with open("scripts/copaw/jarvis_daemon.py", "w") as f:
        f.write(final_code)
    print("Merged successfully.")
else:
    print("Could not find markers.")
