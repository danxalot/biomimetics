from tools.mcp_semantic_search import semantic_search_tool
import json

print("--- Testing Store Memory ---")
try:
    mid = semantic_search_tool.store_memory("The Project Codename is Project Bluebook.", {"category": "test"})
    print(f"Stored Memory ID: {mid}")
except Exception as e:
    print(f"Store Failed: {e}")
    exit(1)

print("\n--- Testing Search Memory ---")
try:
    results = semantic_search_tool.search_memories("What is the project codename?", limit=1)
    print(json.dumps(results, indent=2))
    found = False
    for r in results:
        if "Bluebook" in r["content"]:
            found = True
            break
    if found:
        print("SUCCESS: Found the memory!")
    else:
        print("FAILURE: Did not find the memory.")
except Exception as e:
    print(f"Search Failed: {e}")
    exit(1)
