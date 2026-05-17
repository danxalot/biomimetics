diff --git a/scripts/archivist/semantic_llm_tagger.py b/scripts/archivist/semantic_llm_tagger.py
index 0b4a64b..6575df8 100755
--- a/scripts/archivist/semantic_llm_tagger.py
+++ b/scripts/archivist/semantic_llm_tagger.py
@@ -24,6 +24,7 @@ DOCS_DIR = "/Users/danexall/biomimetics/docs"
 CREDENTIALS_SERVER = "http://localhost:8089"
 RATE_LIMIT_DELAY = 6.0  # 6-second heartbeat for safe RPM/TPM pacing
 MIN_WORDS_PER_PARAGRAPH = 20  # Minimum words to trigger semantic tagging
+MODEL_ID = "gemini-1.5-flash"
 
 # --------------------------------------------------------------------------
 # HIERARCHICAL TAXONOMY: domain -> area -> descriptor leaves
@@ -142,24 +143,24 @@ def route_domain(filepath, content):
     return "bios", None  # default
 
 def build_prompt(domain, payload_text):
-    """Returns (system_text, contents_list) for Gemma 4. Domain is locked by routing,
+    """Returns contents_list for Gemma 4. Domain is locked by routing,
     so the model only ever chooses area + descriptor from a small constrained set."""
     taxonomy_block = render_taxonomy_block(domain)
     shot = FEWSHOT[domain]
 
-    # Single declarative sentence. No rules, no constraints — those trigger reasoning.
-    system_text = "You convert numbered paragraph lists to tag JSON."
+    # Merged system text into the first user message to avoid 500 errors on Gemma models
+    system_text = "You convert numbered paragraph lists to tag JSON. Output ONLY valid JSON. Do not include markdown formatting, reasoning, or backticks."
 
     # Build the user turn shape that the fake-prior-turn will mirror.
     real_user = f"Tags:\n{taxonomy_block}\n\n{payload_text}"
-    shot_user = f"Tags:\n{taxonomy_block}\n\n{shot['user']}"
+    shot_user = f"{system_text}\n\nTags:\n{taxonomy_block}\n\n{shot['user']}"
 
     contents = [
         {"role": "user",  "parts": [{"text": shot_user}]},
         {"role": "model", "parts": [{"text": shot["model"]}]},
         {"role": "user",  "parts": [{"text": real_user}]},
     ]
-    return system_text, contents
+    return contents
 
 def fetch_api_key():
     """Fetch Gemini API key from Credentials Server."""
@@ -183,7 +184,7 @@ def fetch_api_key():
 
 def _scrub_to_json(raw_text):
     """Quad-armoured JSON extraction for Gemma 4 output drift.
-    Gemma 4 emits a `<|channel>thought\\n...<channel|>` wrapper even when thinking is
+    Gemma 4 emits a <|channel>thought\n...<channel|> wrapper even when thinking is
     disabled (empty block in that case). Strip it before anything else."""
     if not raw_text:
         return None
@@ -197,262 +198,153 @@ def _scrub_to_json(raw_text):
     s = s.strip()
 
     # Strip markdown code fences (```json ... ``` or ``` ... ```)
-    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL | re.IGNORECASE)
+    fence = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```$", s, re.DOTALL)
     if fence:
         s = fence.group(1).strip()
-
-    # Direct parse
+    
+    # Final scrub: ensure we have something starting with { or [
+    start = s.find("{")
+    if start == -1: start = s.find("[")
+    
+    end = s.rfind("}")
+    if end == -1: end = s.rfind("]")
+    
+    if start != -1 and end != -1:
+        s = s[start:end+1]
+    
     try:
         return json.loads(s)
-    except json.JSONDecodeError:
-        pass
-
-    # Greedy extract: first '{' to last '}'
-    first = s.find("{")
-    last = s.rfind("}")
-    if first != -1 and last > first:
-        candidate = s[first:last + 1]
-        try:
-            return json.loads(candidate)
-        except json.JSONDecodeError:
-            # Common Gemma drift: trailing commas, single quotes
-            cleaned = re.sub(r",(\s*[}\]])", r"\1", candidate)
-            cleaned = cleaned.replace("'", '"')
-            try:
-                return json.loads(cleaned)
-            except json.JSONDecodeError:
-                return None
-    return None
-
-
-def invoke_gemma(api_key, system_text, contents, target_model):
-    """Gemma 4 call. Uses native `system` role. Thinking is disabled by NOT prefixing
-    the system prompt with `<|think|>`. Greedy decoding (temp=0, topK=1) to suppress
-    any residual stochastic drift into the (empty) thought channel."""
-
-    # Choke-point: 6s pause for 15 RPM compliance
-    time.sleep(RATE_LIMIT_DELAY)
-
-    ctx = ssl.create_default_context()
-    ctx.check_hostname = False
-    ctx.verify_mode = ssl.CERT_NONE
+    except Exception as e:
+        print(f"  ⚠ JSON parse error: {e}")
+        return None
 
-    payload_dict = {
-        "systemInstruction": {"parts": [{"text": system_text}]},
+def invoke_gemma(api_key, contents):
+    """Call Google Generative AI API (Gemma 4)."""
+    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={api_key}"
+    
+    payload = {
         "contents": contents,
         "generationConfig": {
-            "temperature": 0.0,
-            "topK": 1,
-            "topP": 1.0,
-            "candidateCount": 1,
-            "maxOutputTokens": 131072,
-            # Force JSON output at the API level. Supported on Gemini models on this
-            # endpoint; Gemma 4 may also support it. If not, we get a fast HTTP 400.
-            "response_mime_type": "application/json",
-            "stopSequences": ["```", "\n\nInput:", "\n\nAllowed", "Themes:"],
-        },
+            "temperature": 0.1,
+            "maxOutputTokens": 8192,
+            "topP": 0.95,
+        }
     }
-
-    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
-    data = json.dumps(payload_dict).encode("utf-8")
+    
     req = urllib.request.Request(
         url,
-        headers={"Content-Type": "application/json"},
-        data=data,
+        data=json.dumps(payload).encode("utf-8"),
+        headers={"Content-Type": "application/json"}
     )
-
+    
     try:
-        with urllib.request.urlopen(req, context=ctx, timeout=600) as r:
-            resp_data = json.loads(r.read().decode())
-    except urllib.error.HTTPError as e:
-        body = e.read().decode()[:800]
-        print(f"    ❌ HTTP Error {e.code}: {body}")
-        if e.code == 400 and "response_mime_type" in body:
-            print("    ℹ response_mime_type not supported by this model — remove it from generationConfig.")
-        return "ERROR"
+        ctx = ssl.create_default_context()
+        ctx.check_hostname = False
+        ctx.verify_mode = ssl.CERT_NONE
+        
+        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
+            data = json.loads(resp.read().decode("utf-8"))
+            if "candidates" in data and data["candidates"]:
+                return data["candidates"][0]["content"]["parts"][0]["text"]
+            return None
     except Exception as e:
-        print(f"    ❌ Network Error: {e}")
-        return "ERROR"
-
-    candidates = resp_data.get("candidates") or []
-    if not candidates:
-        print(f"    ❌ No candidates. Raw: {json.dumps(resp_data)[:400]}")
-        return "ERROR"
-
-    candidate = candidates[0]
-    finish = candidate.get("finishReason", "")
-    if "content" not in candidate:
-        print(f"    ❌ API blocked (finish={finish}): {json.dumps(candidate)[:400]}")
-        return "ERROR"
-
-    parts = candidate["content"].get("parts") or []
-    raw_text = "".join(p.get("text", "") for p in parts).strip()
-
-    parsed = _scrub_to_json(raw_text)
-    if parsed is not None:
-        if finish == "MAX_TOKENS":
-            print("    ⚠ Output hit MAX_TOKENS — JSON may be truncated/partial.")
-        return parsed
-
-    print("    ❌ Could not extract JSON from Gemma output.")
-    print("    --- RAW LLM OUTPUT START ---")
-    print(raw_text[:2000])
-    print("    --- RAW LLM OUTPUT END ---")
-    return "ERROR"
+        print(f"  ⚠ API call failed: {e}")
+        return None
 
-def scrub_content(content):
-    """Surgically strip all legacy/prior tags from the body."""
-    # Strip inline tags (any domain in our hierarchy + legacy 'context', plus '#host/*')
-    tag_pattern = r'#(context|email|bios|arca|pythia|host|source)/[\w/-]+'
-    content = re.sub(tag_pattern, '', content)
-    
-    # Strip standalone tags line
-    content = re.sub(r'^(tags|Tags):[ \t]*.*$', '', content, flags=re.MULTILINE)
+def process_file(fpath, api_key):
+    """Process a single markdown file: partition, tag, and reassemble."""
+    print(f"▶ Processing: {os.path.basename(fpath)}")
     
-    # Clean up empty lines
-    content = re.sub(r'\n{3,}', '\n\n', content)
-    return content.strip()
+    try:
+        with open(fpath, "r", encoding="utf-8") as f:
+            content = f.read()
+    except Exception as e:
+        print(f"  ⚠ Read error: {e}")
+        return False
 
-def update_frontmatter(content, tags):
-    """Overwrite existing YAML frontmatter tags with the aggregate list."""
-    tag_list_str = ", ".join([f'"{t}"' for t in tags])
+    domain, host = route_domain(fpath, content)
     
-    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
+    lines = content.split("\n")
+    paragraphs = []
+    current_para = []
+    in_fence = False
     
-    if frontmatter_match:
-        yaml_content = frontmatter_match.group(1)
-        if re.search(r"^tags:", yaml_content, re.MULTILINE):
-            new_yaml = re.sub(r"^tags:.*$", f"tags: [{tag_list_str}]", yaml_content, flags=re.MULTILINE)
-        else:
-            new_yaml = yaml_content.strip() + f"\ntags: [{tag_list_str}]"
-        return content.replace(yaml_content, new_yaml)
-    else:
-        return f"---\ntags: [{tag_list_str}]\n---\n\n" + content
-
-def derive_frontmatter_tags(domain, host, per_paragraph_tags):
-    """Build the 3 document-level identity tags from inline paragraph tags.
-    Rules:
-      tag 1 = #<domain>
-      tag 2 = most-common #<domain>/<area>
-      tag 3 = #host/<host> for pythia, else next-most-common area (or modal descriptor)
-    """
-    from collections import Counter
-    area_counter = Counter()
-    descriptor_counter = Counter()
-    for tags in per_paragraph_tags:
-        for t in tags:
-            parts = t.strip("#").split("/")
-            if len(parts) == 2:
-                area_counter[t] += 1
-            elif len(parts) == 3:
-                descriptor_counter[t] += 1
-                # The area implicit in this descriptor also counts
-                area_counter[f"#{parts[0]}/{parts[1]}"] += 1
-
-    out = [f"#{domain}"]
-    if area_counter:
-        out.append(area_counter.most_common(1)[0][0])
-
-    if domain == "pythia" and host:
-        out.append(f"#host/{host}")
-    else:
-        # Prefer second-most-common area; fall back to top descriptor
-        if len(area_counter) >= 2:
-            out.append(area_counter.most_common(2)[1][0])
-        elif descriptor_counter:
-            out.append(descriptor_counter.most_common(1)[0][0])
+    for i, line in enumerate(lines):
+        if i == 0 and line.strip() == "---" and not in_fence:
+            paragraphs.append({"type": "protected", "text": line})
+            in_fence = "yaml"
+            continue
+        if in_fence == "yaml":
+            paragraphs[-1]["text"] += "\n" + line
+            if line.strip() == "---": in_fence = False
+            continue
+            
+        if line.strip().startswith("```"):
+            if not in_fence:
+                if current_para:
+                    paragraphs.append({"type": "text", "text": "\n".join(current_para)})
+                    current_para = []
+                paragraphs.append({"type": "protected", "text": line})
+                in_fence = "code"
+            else:
+                paragraphs[-1]["text"] += "\n" + line
+                in_fence = False
+            continue
+        
+        if in_fence == "code":
+            paragraphs[-1]["text"] += "\n" + line
+            continue
+            
+        if line.strip() == "":
+            if current_para:
+                paragraphs.append({"type": "text", "text": "\n".join(current_para)})
+                current_para = []
+            paragraphs.append({"type": "newline", "text": ""})
         else:
-            out.append(f"#{domain}/meta")
-    return out
-
-def process_file(filepath, api_key):
-    """Processes an entire document in 1 API call using Paragraph Mapping."""
-    with open(filepath, "r", encoding="utf-8") as f:
-        original_content = f.read()
-
-    if len(original_content.strip()) < 50:
-        return False
-
-    # Route: content-aware pythia detection + path-based domain fallback
-    domain, host = route_domain(filepath, original_content)
-    # Both Gemma 4 models work; 26B-A4B is faster (MoE). Use it everywhere.
-    target_model = "gemma-4-26b-a4b-it"
-    allowed_leaves = allowed_leaves_for(domain)
-
-    clean_content = scrub_content(original_content)
-    paragraphs = [p.strip() for p in clean_content.split("\n\n") if p.strip()]
-
-    if not paragraphs:
-        return False
-
-    payload_parts = []
-    taggable_count = 0
-    for i, p in enumerate(paragraphs, 1):
-        if len(p.split()) >= MIN_WORDS_PER_PARAGRAPH:
-            payload_parts.append(f"[{i}] {p}")
-            taggable_count += 1
+            current_para.append(line)
+            
+    if current_para:
+        paragraphs.append({"type": "text", "text": "\n".join(current_para)})
 
-    if not payload_parts:
-        print(f"  ▶ Processing: {os.path.basename(filepath)}")
-        print(f"    ⚠ Skipped: No paragraphs meet the {MIN_WORDS_PER_PARAGRAPH}-word threshold.")
+    text_indices = [i for i, p in enumerate(paragraphs) if p["type"] == "text" and len(p["text"].split()) >= MIN_WORDS_PER_PARAGRAPH]
+    
+    if not text_indices:
+        print("  ○ No eligible paragraphs found.")
         return False
 
-    payload_text = "\n\n".join(payload_parts)
-
-    host_label = f" (host={host})" if host else ""
-    print(f"  ▶ Processing: {os.path.basename(filepath)}")
-    print(f"    🔒 Domain: {domain}{host_label} | Taggable: {taggable_count}/{len(paragraphs)} | Heartbeat: {RATE_LIMIT_DELAY}s")
-
-    system_text, contents = build_prompt(domain, payload_text)
-    result = invoke_gemma(api_key, system_text, contents, target_model)
-
-    if result == "ERROR" or result is None:
-        print(f"    ❌ Failed to tag file. Halting further attempts on this file.")
+    payload_text = "\n\n".join(f"[{i+1}] {paragraphs[idx]['text']}" for i, idx in enumerate(text_indices))
+    prompt_contents = build_prompt(domain, payload_text)
+    
+    raw_response = invoke_gemma(api_key, prompt_contents)
+    if not raw_response:
         return False
-
-    json_response = result
-    if not json_response or not isinstance(json_response, dict):
-        print(f"    ❌ Invalid response format received.")
+        
+    tag_map = _scrub_to_json(raw_response)
+    if not tag_map:
         return False
+        
+    modified = False
+    for i, idx in enumerate(text_indices):
+        key = str(i + 1)
+        if key in tag_map:
+            tags = tag_map[key]
+            if isinstance(tags, list) and tags:
+                tag_string = " " + " ".join(tags)
+                paragraphs[idx]["text"] += tag_string
+                modified = True
+                
+    if modified:
+        reassembled = "\n".join(p["text"] for p in paragraphs)
+        with open(fpath, "w", encoding="utf-8") as f:
+            f.write(reassembled)
+        print(f"  ✅ Tags injected.")
+        return True
+    
+    return False
 
-    # Apply tags inline. Enforce exactly 3 tags per paragraph, all from the
-    # constrained domain taxonomy. Hallucinated tags are dropped.
-    tagged_paragraphs = []
-    per_paragraph_tags = []
-
-    for i, p in enumerate(paragraphs, 1):
-        idx_str = str(i)
-        if idx_str in json_response and isinstance(json_response[idx_str], list):
-            p_tags = [
-                t.strip() for t in json_response[idx_str]
-                if isinstance(t, str) and t.strip() in allowed_leaves
-            ][:3]
-            if p_tags:
-                tagged_paragraphs.append(f"{p}\n{' '.join(p_tags)}")
-                per_paragraph_tags.append(p_tags)
-            else:
-                tagged_paragraphs.append(p)
-        else:
-            tagged_paragraphs.append(p)
-
-    # Derive 3 document-level frontmatter tags from the inline tags
-    if per_paragraph_tags:
-        frontmatter_tags = derive_frontmatter_tags(domain, host, per_paragraph_tags)
-    else:
-        frontmatter_tags = [f"#{domain}", f"#{domain}/meta", f"#{domain}/meta/uncategorized"]
-
-    final_body = "\n\n".join(tagged_paragraphs)
-    final_content = update_frontmatter(final_body, frontmatter_tags)
-
-    with open(filepath, "w", encoding="utf-8") as f:
-        f.write(final_content)
-
-    print(f"    ✅ Tagged {len(tagged_paragraphs)} paragraphs | Frontmatter: {' '.join(frontmatter_tags)}")
-    return True
-
-def run_vault_sweep():
+def main():
     print("="*60)
-    print("  BiOS Semantic Tagger v2.1.0 (High-Speed Array Mapping)")
+    print("  BiOS Semantic LLM Tagger (v2.1.0) - Flash Mode")
     print("="*60)
 
     api_key = fetch_api_key()
@@ -460,20 +352,14 @@ def run_vault_sweep():
         print("❌ Critical Error: Could not locate Gemini API Key.")
         return
 
-    search_pattern = os.path.join(DOCS_DIR, "**", "*.md")
-    files = glob.glob(search_pattern, recursive=True)
+    files = glob.glob(os.path.join(DOCS_DIR, "**", "*.md"), recursive=True)
     
-    modified_count = 0
     for fpath in files:
-        if any(x in fpath for x in ["staging", ".archive", "MOC"]): continue
-        filename = os.path.basename(fpath)
-        if filename in ["SWARM_LEDGER.md", "ACTIVE_LEGAL_CASES.md"]: continue
-
-        if process_file(fpath, api_key):
-            modified_count += 1
-
-    print("="*60)
-    print(f"Sweep Complete. Successfully analyzed and updated {modified_count} files.")
+        if any(x in fpath for x in ["obsidian_staging", ".archive", "MOC", "MASTER_"]):
+            continue
+        
+        process_file(fpath, api_key)
+        time.sleep(RATE_LIMIT_DELAY)
 
 if __name__ == "__main__":
-    run_vault_sweep()
\ No newline at end of file
+    main()
\ No newline at end of file
