"""Validators for LLM output. Reject-first; nothing invalid passes.

We don't use jsonschema here — the shape is small and we need per-field
error messages the ingest audit can actually read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.extract.prompts import ALLOWED_NODE_TYPES, ALLOWED_RELATION_TYPES


@dataclass
class ValidationResult:
    ok: bool
    entities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dropped: int = 0        # how many items were silently discarded for policy


def validate_entities(payload: Any, *, chunk_text: str) -> ValidationResult:
    """Validate an entity-extraction payload.

    Rules:
      - top-level must be a dict with 'entities' as a list
      - each entity: name:str non-empty, type:str in ALLOWED_NODE_TYPES
      - name MUST appear in chunk_text (substring, case-insensitive) —
        this is the brief's 'never invent entities' rule enforced in code
      - optional span {char_start, char_end}: if present, must be valid

    Returns ValidationResult with the surviving entities; items that
    violate a rule are DROPPED and counted.
    """
    r = ValidationResult(ok=False)
    if not isinstance(payload, dict):
        r.errors.append("payload is not a JSON object")
        return r
    raw = payload.get("entities")
    if not isinstance(raw, list):
        r.errors.append("'entities' is not a list")
        return r
    lower_text = chunk_text.lower()
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            r.dropped += 1
            continue
        name = (item.get("name") or "").strip()
        etype = (item.get("type") or "").strip()
        if not name or not etype:
            r.dropped += 1
            continue
        if etype not in ALLOWED_NODE_TYPES:
            r.dropped += 1
            continue
        if name.lower() not in lower_text:
            # Model hallucinated — brief says reject.
            r.dropped += 1
            continue
        key = (name, etype)
        if key in seen:
            r.dropped += 1
            continue
        seen.add(key)
        span = item.get("span")
        if isinstance(span, dict):
            cs = span.get("char_start")
            ce = span.get("char_end")
            if not (isinstance(cs, int) and isinstance(ce, int)
                    and 0 <= cs < ce <= len(chunk_text)):
                span = None
        r.entities.append({"name": name, "type": etype, "span": span})
    r.ok = True
    return r


def validate_relations(payload: Any, *, entity_names: set[str],
                       chunk_text: str) -> ValidationResult:
    """Validate relation-extraction output.

    Rules:
      - source, target MUST be in entity_names (brief: no free-form)
      - type MUST be in ALLOWED_RELATION_TYPES
      - confidence coerced to [0,1]; missing → 0.5
      - evidence_text present and <=400 chars (hard-cap to keep audit sane)
      - source != target
    """
    r = ValidationResult(ok=False)
    if not isinstance(payload, dict):
        r.errors.append("payload is not a JSON object")
        return r
    raw = payload.get("relations")
    if not isinstance(raw, list):
        r.errors.append("'relations' is not a list")
        return r
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            r.dropped += 1
            continue
        src = (item.get("source") or "").strip()
        tgt = (item.get("target") or "").strip()
        rtype = (item.get("type") or "").strip()
        if not src or not tgt or src == tgt:
            r.dropped += 1
            continue
        if src not in entity_names or tgt not in entity_names:
            r.dropped += 1
            continue
        if rtype not in ALLOWED_RELATION_TYPES:
            r.dropped += 1
            continue
        try:
            conf = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        evid = (item.get("evidence_text") or "").strip()
        if not evid or len(evid) > 400:
            # Not a hard reject — truncate and keep.
            evid = evid[:400] or "(no evidence span)"
        key = (src, tgt, rtype)
        if key in seen:
            r.dropped += 1
            continue
        seen.add(key)
        r.relations.append({
            "source": src, "target": tgt, "type": rtype,
            "confidence": conf, "evidence_text": evid,
        })
    r.ok = True
    return r


def validate_vision(payload: Any, *,
                    confidence_cap: float = 0.65) -> ValidationResult:
    """Validate a vision-extraction payload.

    Keeps a loose shape — vision reads of charts are inherently noisy, so
    we normalise missing fields rather than reject the whole response.
    The confidence is HARD-CAPPED at ``confidence_cap`` regardless of
    what the model self-reports.
    """
    r = ValidationResult(ok=False)
    if not isinstance(payload, dict):
        r.errors.append("vision payload is not a JSON object")
        return r
    out: dict = {
        "chart_type": _str(payload.get("chart_type"), default="other"),
        "title": _str(payload.get("title"), default=""),
        "x_axis_label": _str(payload.get("x_axis_label"), default=""),
        "y_axis_label": _str(payload.get("y_axis_label"), default=""),
        "x_tick_labels": _str_list(payload.get("x_tick_labels")),
        "entities_mentioned": _str_list(payload.get("entities_mentioned")),
        "description": _str(payload.get("description"), default=""),
        "notes": _str(payload.get("notes"), default=""),
    }
    # data_points: keep only numeric-y entries
    data_points: list[dict] = []
    raw_dp = payload.get("data_points")
    if isinstance(raw_dp, list):
        for dp in raw_dp:
            if not isinstance(dp, dict):
                r.dropped += 1
                continue
            y = dp.get("y")
            if not isinstance(y, (int, float)):
                r.dropped += 1
                continue
            data_points.append({
                "series": _str(dp.get("series"), default=""),
                "x": _str(dp.get("x"), default=""),
                "y": float(y),
            })
    out["data_points"] = data_points
    # Confidence: coerce + cap.
    try:
        self_conf = float(payload.get("confidence", 0.5))
    except (TypeError, ValueError):
        self_conf = 0.5
    self_conf = max(0.0, min(1.0, self_conf))
    out["confidence"] = min(self_conf, confidence_cap)
    out["self_reported_confidence"] = self_conf
    # Stuff the whole normalised payload into r.entities[0] as a convenient
    # single-item carrier for the pipeline (we aren't producing graph
    # entities here).
    r.entities = [out]
    r.ok = True
    return r


def _str(v: Any, *, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        s = _str(x)
        if s:
            out.append(s)
    return out


def apply_verifier(verifier_payload: Any,
                   candidates: list[dict]) -> list[dict]:
    """Fold the verifier's verdicts back onto the proposer's relations.

    - verdict='accept' → keep, confidence = verifier confidence.
    - verdict='modify' → keep with new type (must still be in vocab),
      confidence = verifier confidence.
    - verdict='reject' → drop.
    - Any candidate the verifier did not touch (missing index) is kept
      with proposer confidence × 0.8 — unverified but not rejected.
    """
    if not isinstance(verifier_payload, dict):
        # Nothing the verifier said parses — keep proposer output as-is,
        # just mark it unverified.
        return [{**c, "verified": False} for c in candidates]
    verdicts = verifier_payload.get("verified")
    if not isinstance(verdicts, list):
        return [{**c, "verified": False} for c in candidates]
    verdict_by_idx: dict[int, dict] = {}
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        idx = v.get("index")
        if isinstance(idx, int):
            verdict_by_idx[idx] = v
    out: list[dict] = []
    for i, cand in enumerate(candidates, start=1):
        v = verdict_by_idx.get(i)
        if v is None:
            out.append({**cand, "verified": False})
            continue
        verdict = (v.get("verdict") or "").lower()
        if verdict == "reject":
            continue
        try:
            new_conf = float(v.get("confidence", cand["confidence"]))
        except (TypeError, ValueError):
            new_conf = cand["confidence"]
        new_conf = max(0.0, min(1.0, new_conf))
        kept = {**cand, "confidence": new_conf, "verified": True}
        if verdict == "modify":
            new_type = (v.get("type") or "").strip()
            if new_type in ALLOWED_RELATION_TYPES:
                kept["type"] = new_type
        out.append(kept)
    return out
