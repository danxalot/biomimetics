import re
with open('services/geometry_heavy_lifter/core.py', 'r') as f:
    core_content = f.read()

# Add batch worker functions right after _phase2_worker
batch_workers = """
def _phase1_batch_worker(model_name: str, batch_data: List[Dict], objective: str):
    import logging
    import json
    from PIL import Image
    from vllm import LLM
    
    worker_log = logging.getLogger("Phase1BatchWorker")
    worker_log.info(f"Loading embedder ONCE for batch: {model_name}")
    
    llm_embed = LLM(
        model=model_name,
        runner="pooling",
        trust_remote_code=True,
        gpu_memory_utilization=0.90,
        max_model_len=8192,
    )
    
    for item in batch_data:
        text_chunks = item["text_chunks"]
        image_crops = item["image_crops"]
        checkpoint_path = item["checkpoint_path"]
        book_name = item["book_name"]
        
        worker_log.info(f"Embedding book: {book_name} ({len(text_chunks)} text, {len(image_crops)} images)")
        
        sanitized_chunks = []
        for c in text_chunks:
            c_str = str(c)
            clean_c = c_str.replace("<|vision_start|>", "").replace("<|image_pad|>", "").replace("<|vision_end|>", "")
            sanitized_chunks.append(clean_c)

        text_vectors = []
        if sanitized_chunks:
            text_embed_inputs = [f"Instruct: {objective}\\nText: {c[:3000]}" for c in sanitized_chunks]
            text_embed_outputs = llm_embed.embed(text_embed_inputs)
            text_vectors = [o.outputs.embedding for o in text_embed_outputs]
        
        image_vectors = []
        if image_crops:
            inputs = []
            for crop in image_crops:
                prompt = f"<|vision_start|><|image_pad|><|vision_end|>Instruct: {objective}\\nText: Represent this diagram as an embedding."
                img_path = crop.get("image_path")
                img = Image.open(img_path).convert("RGB")
                if max(img.size) > 1568:
                    ratio = 1568 / max(img.size)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
                inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})
                
            image_embed_outputs = llm_embed.embed(inputs)
            image_vectors = [o.outputs.embedding for o in image_embed_outputs]
            
        with open(checkpoint_path, "w") as f:
            json.dump({"text_vectors": text_vectors, "image_vectors": image_vectors}, f)


def _phase2_batch_worker(model_name: str, batch_data: List[Dict], objective: str):
    import logging
    import json
    from PIL import Image
    from vllm import LLM, SamplingParams
    
    worker_log = logging.getLogger("Phase2BatchWorker")
    worker_log.info(f"Loading instruct model ONCE for batch: {model_name}")
    
    llm_instruct = LLM(
        model=model_name,
        dtype="half",
        trust_remote_code=True,
        gpu_memory_utilization=0.90,
        max_model_len=8192,
        disable_log_stats=True,
    )
    sp = SamplingParams(temperature=0.1, max_tokens=2048, stop=["<|endoftext|>", "```\\n"])
    
    for item in batch_data:
        text_chunks = item["text_chunks"]
        image_crops = item["image_crops"]
        output_path = item["output_path"]
        book_name = item["book_name"]
        
        worker_log.info(f"Instruct processing book: {book_name} ({len(text_chunks)} text, {len(image_crops)} images)")
        
        text_outputs = []
        if text_chunks:
            text_prompts = []
            for c in text_chunks:
                c_str = str(c)
                system = (
                    f"Objective: {objective}. "
                    "Extract key geometric concepts from the following passage. "
                    "Output JSON ONLY: "
                    '{{"objects": [{{"id": "ConceptName", "desc": "description", "mass": 0.5}}]}}'
                )
                prompt = (
                    f"<|im_start|>system\\n{system}<|im_end|>\\n"
                    f"<|im_start|>user\\n{c_str[:3000]}<|im_end|>\\n"
                    f"<|im_start|>assistant\\n"
                )
                text_prompts.append(prompt)
                
            text_outputs_raw = llm_instruct.generate(text_prompts, sp)
            text_outputs = [o.outputs[0].text for o in text_outputs_raw]
        
        image_outputs = []
        if image_crops:
            inputs = []
            for crop in image_crops:
                caption = crop.get("caption", "")
                cap_note = f' Caption: "{caption}".' if caption else ""
                system = (
                    f"Objective: {objective}.{cap_note} "
                    "Examine this geometric diagram carefully. "
                    "Extract every distinct geometric concept, mathematical relationship, "
                    "or structural pattern visible. "
                    "Output JSON ONLY: "
                    '{{"objects": [{{"id": "ConceptName", "desc": "precise description", "mass": 25.0}}]}}'
                )
                prompt = (
                    f"<|im_start|>system\\n{system}<|im_end|>\\n"
                    "<|im_start|>user\\n"
                    "<|vision_start|><|image_pad|><|vision_end|>"
                    "Examine this diagram and extract geometric concepts as JSON."
                    "<|im_end|>\\n"
                    "<|im_start|>assistant\\n"
                )
                img = Image.open(crop["image_path"]).convert("RGB")
                max_side = 1568
                if max(img.size) > max_side:
                    ratio = max_side / max(img.size)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
                inputs.append({"prompt": prompt, "multi_modal_data": {"image": img}})
                
            image_outputs_raw = llm_instruct.generate(inputs, sp)
            image_outputs = [o.outputs[0].text for o in image_outputs_raw]
            
        with open(output_path, "w") as f:
            json.dump({"text_outputs": text_outputs, "image_outputs": image_outputs}, f)
"""

core_content = core_content.replace(
    "class HeavyGeometryIngester:",
    batch_workers + "\n\nclass HeavyGeometryIngester:"
)

batch_process_method = """
    def batch_process_files(self, refined_doc_paths: List[str], objective: str = "Extract geometric concepts") -> Dict[str, Dict]:
        \"\"\"
        Process multiple refined documents in three heavy sequential batches, loading the LLMs once.
        Returns a dict mapping book_name to stats.
        \"\"\"
        from services.geometry_kernel.clever_artifacts import extract_clever_artifacts
        t_start = time.time()
        
        batch_1_data = [] # For Embed
        batch_2_data = [] # For Instruct
        assembly_data = [] # For PCA & Merge
        
        logger.info(f"=== BATCH PROCESSING {len(refined_doc_paths)} DOCUMENTS ===")
        
        for refined_doc_path in refined_doc_paths:
            with open(refined_doc_path) as f:
                rd = json.load(f)
            book_name = rd["book_name"]
            text_chunks = rd["text_chunks"]
            image_crops = rd["image_crops"]
            refined_doc_dir = Path(refined_doc_path).parent
            
            # Resolve image paths
            for crop in image_crops:
                p = crop["image_path"]
                if not os.path.isabs(p):
                    crop["image_path"] = str(refined_doc_dir / p)
                elif not os.path.exists(p):
                    parts = Path(p).parts
                    relative = Path(*parts[-3:])
                    remapped = str(refined_doc_dir / relative)
                    crop["image_path"] = remapped
            
            vectors_checkpoint = refined_doc_dir / "phase1_vectors.json"
            phase2_output_file = refined_doc_dir / "phase2_outputs.json"
            
            assembly_data.append({
                "book_name": book_name,
                "text_chunks": text_chunks,
                "image_crops": image_crops,
                "vectors_checkpoint": vectors_checkpoint,
                "phase2_output_file": phase2_output_file,
                "refined_doc_dir": refined_doc_dir,
                "refined_doc_path": refined_doc_path
            })
            
            # Check if Embed is needed
            checkpoint_valid = vectors_checkpoint.exists() and vectors_checkpoint.stat().st_mtime >= Path(refined_doc_path).stat().st_mtime
            if not checkpoint_valid:
                if vectors_checkpoint.exists(): vectors_checkpoint.unlink()
                batch_1_data.append({
                    "book_name": book_name, "text_chunks": text_chunks, "image_crops": image_crops,
                    "checkpoint_path": str(vectors_checkpoint)
                })
            else:
                logger.info(f"  [Embed SKIP] {book_name}")
                
            # Embed determines if Instruct is needed. If we are running Instruct, we just do it. Wait, phase2 doesn't have a permanent checkpoint, it deletes it.
            # But what if the final Objects.json exists? The Modal orchestration script handles checking if Objects.json exists BEFORE calling this batch.
            # So anything in refined_doc_paths NEEDS Phase 2 (and Phase 3).
            batch_2_data.append({
                "book_name": book_name, "text_chunks": text_chunks, "image_crops": image_crops,
                "output_path": str(phase2_output_file)
            })

        # --- PHASE 1: BATCH EMBED ---
        if batch_1_data:
            logger.info(f"--- BATCH PHASE 1: Launching Embedder for {len(batch_1_data)} books ---")
            ctx = mp.get_context("spawn")
            p1 = ctx.Process(target=_phase1_batch_worker, args=(EMBED_MODEL, batch_1_data, objective))
            p1.start()
            p1.join()
            if p1.exitcode != 0:
                raise RuntimeError("Batch Phase 1 Embedder crashed.")
        
        # --- PHASE 2: BATCH INSTRUCT ---
        if batch_2_data:
            logger.info(f"--- BATCH PHASE 2: Launching Instruct for {len(batch_2_data)} books ---")
            ctx = mp.get_context("spawn")
            p2 = ctx.Process(target=_phase2_batch_worker, args=(INSTRUCT_MODEL, batch_2_data, objective))
            p2.start()
            p2.join()
            if p2.exitcode != 0:
                raise RuntimeError("Batch Phase 2 Instruct crashed.")

        # --- PHASE 3: ASSEMBLY & OUTPUT ---
        logger.info(f"--- BATCH PHASE 3: Assembly & PCA for {len(assembly_data)} books ---")
        final_stats = {}
        for item in assembly_data:
            book_name = item["book_name"]
            
            with open(item["vectors_checkpoint"]) as _f:
                _vc = json.load(_f)
            text_vectors = _vc["text_vectors"]
            image_vectors = _vc["image_vectors"]
            
            with open(item["phase2_output_file"]) as _f:
                p2_result = json.load(_f)
            text_outputs_texts = p2_result["text_outputs"]
            image_outputs_texts = p2_result["image_outputs"]
            
            if item["phase2_output_file"].exists():
                item["phase2_output_file"].unlink()
                
            image_objects = []
            if item["image_crops"]:
                image_objects = self._parse_image_outputs(image_outputs_texts, item["image_crops"], image_vectors)
                
            all_vectors = text_vectors + image_vectors
            projected = self._pca_project(all_vectors)
            
            objects_list = []
            for i, text in enumerate(text_outputs_texts):
                parsed = self._robust_parse(text)
                for obj in parsed.get("objects", []):
                    obj.setdefault("mass", 0.5)
                    obj.setdefault("source", "text")
                    obj["vector"] = text_vectors[i]
                    obj["position"] = projected[i]
                    objects_list.append(obj)
                    
            for j, obj in enumerate(image_objects):
                crop_idx = obj.pop("_crop_idx", j % len(image_vectors))
                obj.setdefault("mass", 25.0)
                obj.setdefault("source", "image")
                vi = len(text_vectors) + crop_idx
                obj["vector"] = image_vectors[crop_idx]
                obj["position"] = projected[vi] if vi < len(projected) else [0.0, 0.0, 0.0]
                objects_list.append(obj)
                
            safe_name = book_name.replace(" ", "_").replace("/", "_")
            out_dir = f"{self.storage_root}/atomized/Concepts/{safe_name}"
            os.makedirs(out_dir, exist_ok=True)
            
            with open(f"{out_dir}/Vectors.json", "w") as f: json.dump(all_vectors, f)
            with open(f"{out_dir}/Objects.json", "w") as f: json.dump(objects_list, f, indent=2)
            
            geometric_model = {"objects": objects_list, "trajectory": [0, 0, 0]}
            artifacts_data = None
            try:
                artifacts = extract_clever_artifacts(geometric_model, "\\n".join(str(c) for c in item["text_chunks"][:50]))
                artifacts_data = artifacts if isinstance(artifacts, dict) else artifacts.to_dict()
                with open(f"{out_dir}/Artifacts.json", "w") as f:
                    json.dump(artifacts_data, f, indent=2)
            except Exception as _e:
                logger.warning(f"Artifacts skip: {_e}")
                
            if item["vectors_checkpoint"].exists():
                item["vectors_checkpoint"].unlink()
                
            stats = {
                "book": book_name,
                "text_objects": len(objects_list) - len(image_objects),
                "image_objects": len(image_objects),
                "total_objects": len(objects_list),
                "output_data": {"objects": objects_list, "vectors": all_vectors, "artifacts": artifacts_data}
            }
            final_stats[book_name] = stats
            
        logger.info(f"=== BATCH PROCESSING COMPLETE in {time.time()-t_start:.1f}s ===")
        return final_stats
"""

core_content = core_content.replace(
    "    # Internal helpers",
    batch_process_method + "\n\n    # Internal helpers"
)

with open('services/geometry_heavy_lifter/core.py', 'w') as f:
    f.write(core_content)
