#!/usr/bin/env python3
"""Origin (where a note came from) vs partition (which graph it belongs in).

These are different axes and must not be collapsed:

  source/grok | source/claude | source/antigravity | source/zed | source/notion
      provenance — which IDE/agent produced the artifact

  #partition/bios | arca | pythia | life | grants
      knowledge-graph slice — where retrieval should look

IDE logs that *mention* Hopfield/JEPA are still BiOS work-logs. Pythia partition
is for documents that *are* Pythia (path /pythia/, or a dedicated pythia source).
"""

from __future__ import annotations

import re
from pathlib import Path

ORIGIN_TAGS = {
    "grok": "source/grok",
    "claude": "source/claude",
    "antigravity": "source/antigravity",
    "zed": "source/zed",
    "notion": "source/notion",
    "manual": "source/manual",
    "bios": "source/bios",
    "arca": "source/arca",
}

_PYTHIA_PATH = re.compile(r"(?:^|/)pythia(?:/|_)", re.I)


def origin_from_path(path: str) -> str | None:
    raw = str(path).replace("\\", "/")
    p = raw.lower()
    name = Path(raw).name.lower()
    if "/raw_dev_artifacts/grok/" in p or "/.grok/" in p or "chat_history" in name:
        return "grok"
    if "/raw_dev_artifacts/claude/" in p or "/.claude/" in p:
        return "claude"
    if (
        "/raw_dev_artifacts/antigravity/" in p
        or "/antigravity/" in p
        or "/.gemini/" in p
        or name in ("walkthrough.md", "implementation_plan.md", "task.md", "analysis_results.md", "status_report.md")
    ):
        return "antigravity"
    if "/raw_dev_artifacts/zed/" in p or "/zed/" in p:
        return "zed"
    if p.startswith("notion://") or "/notion/" in p:
        return "notion"
    if "/arca/" in p or "shared_storage/awake" in p:
        return "arca"
    if "/biomimetics/docs/" in p or name == "architecture_decision_log.md":
        return "bios"
    stem = Path(raw).stem
    if re.search(r"_[0-9]{3,8}$", stem) and "chat_history" not in name:
        return "claude"
    return None


def origin_from_text(content: str) -> str | None:
    m = re.search(r"(?m)^source_tool:\s*([a-zA-Z0-9_-]+)\s*$", content or "")
    if m:
        return m.group(1).strip().lower()
    tags = re.findall(r"(?<!\S)#?source/([a-zA-Z0-9_-]+)", content or "")
    for t in tags:
        tl = t.lower()
        if tl in ORIGIN_TAGS:
            return tl
    return None


def resolve_origin(path: str, content: str = "") -> str | None:
    return origin_from_text(content) or origin_from_path(path)


def is_ide_log(path: str, content: str = "", origin: str | None = None) -> bool:
    o = origin or resolve_origin(path, content)
    if o in ("grok", "claude", "antigravity", "zed"):
        return True
    p = str(path).replace("\\", "/").lower()
    return "/bios/architecture/artifacts/" in p or "/raw_dev_artifacts/" in p


def pythia_by_path(path: str) -> bool:
    p = str(path).replace("\\", "/").lower()
    return bool(_PYTHIA_PATH.search(p))


def stamp_origin(body: str, origin: str, source_path: str) -> str:
    """Ensure YAML + source/* tag + bios partition on a condensed artifact."""
    origin = (origin or "manual").lower()
    tag = ORIGIN_TAGS.get(origin, f"source/{origin}")
    body = (body or "").strip()
    extra = [
        f"source_tool: {origin}",
        f"source_path: {source_path}",
    ]
    if body.startswith("---"):
        parts = body.split("---", 2)
        # ['', yaml, rest]
        yaml_block = parts[1] if len(parts) >= 3 else ""
        rest = parts[2] if len(parts) >= 3 else body
        lines = [ln for ln in yaml_block.splitlines() if ln.strip()]
        keys = {ln.split(":", 1)[0].strip() for ln in lines if ":" in ln}
        for pair in extra:
            k = pair.split(":", 1)[0]
            if k not in keys:
                lines.append(pair)
        if not any(tag in ln for ln in lines):
            inserted = False
            for i, ln in enumerate(lines):
                if ln.startswith("tags:"):
                    lines.insert(i + 1, f"  - {tag}")
                    inserted = True
                    break
            if not inserted:
                lines.append("tags:")
                lines.append(f"  - {tag}")
                lines.append("  - bios/architecture")
        yaml_block = "\n".join(lines) + "\n"
        body = f"---\n{yaml_block}---{rest}"
    else:
        body = (
            "---\n"
            f"source_tool: {origin}\n"
            f"source_path: {source_path}\n"
            "tags:\n"
            f"  - {tag}\n"
            "  - bios/architecture\n"
            "---\n\n" + body
        )
    if "#partition/bios" not in body:
        # insert after frontmatter
        if body.startswith("---"):
            bits = body.split("---", 2)
            rest = bits[2] if len(bits) >= 3 else "\n" + body
            if "#partition/" not in rest:
                rest = "\n#partition/bios\n" + rest
            body = f"---{bits[1]}---{rest}"
        else:
            body = "#partition/bios\n\n" + body
    return body if body.endswith("\n") else body + "\n"


def rewrite_artifact_partitions(path: str, content: str) -> str:
    """Correct mis-filed IDE artifacts: keep origin tags, drop keyword-pythia."""
    origin = resolve_origin(path, content)
    text = content
    if is_ide_log(path, content, origin) and not pythia_by_path(path):
        text = re.sub(r"(?<!\S)#partition/pythia(?:\s+|(?=\n)|$)", "", text)
        if origin != "arca":
            text = re.sub(r"(?<!\S)#partition/arca(?:\s+|(?=\n)|$)", "", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = stamp_origin(text, origin or "manual", path)
    return text
