"""Prompt templates for the two extraction passes.

Design rules (from the brief):
 * Entity extraction and relation extraction are SEPARATE calls — do not
   ask one call to do both.
 * Node types and relation types come from a FIXED vocabulary. The
   prompt restates it and the system prompt orders the model to use it;
   the validator rejects anything out of vocab regardless.
 * Output is JSON only. No prose. Ollama ``format='json'`` enforces it
   at the client level too.
 * The verifier prompt is architecturally different from the proposer:
   it is given the proposer's candidate relations and judges each one
   as accept / reject / modify. It does NOT re-extract from scratch.
"""
from __future__ import annotations

ALLOWED_NODE_TYPES = [
    "SKU", "Component", "Supplier", "Plant", "Site", "Geography",
    "Route", "Port", "Event", "Document", "DataTable",
]
ALLOWED_RELATION_TYPES = [
    "contains", "supplied_by", "manufactured_at", "located_in", "ships_via",
    "disrupted_by", "substitutes_for", "evidenced_by", "has_financials",
]


ENTITY_SYSTEM = (
    "You extract supply-chain entities from short text passages. You "
    "respond with STRICT JSON only, matching the schema the user "
    "provides. You never invent entities not mentioned in the text, "
    "and you never emit entity types outside the fixed vocabulary."
)


def entity_user(text: str, *, source_file: str, chunk_index: int) -> str:
    types = ", ".join(ALLOWED_NODE_TYPES)
    return (
        "Extract entities from the TEXT below. Return JSON of the form:\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": "<as it appears in text>",\n'
        '     "type": "<one of: ' + types + '>",\n'
        '     "span": {"char_start": <int>, "char_end": <int>}}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Only use entity types from the allowed list.\n"
        "- 'name' is a verbatim substring of TEXT. Do NOT paraphrase.\n"
        "- 'span' points at the first occurrence in TEXT.\n"
        "- Deduplicate by (name, type).\n"
        "- If nothing fits, return {\"entities\": []}.\n\n"
        f"SOURCE: {source_file}  CHUNK: {chunk_index}\n\n"
        "TEXT:\n"
        "---\n"
        f"{text}\n"
        "---"
    )


RELATION_SYSTEM = (
    "You extract typed relations between supply-chain entities. You "
    "respond with STRICT JSON only. You never invent relations the TEXT "
    "does not support. You only use relation types from the fixed "
    "vocabulary provided."
)


def relation_user(text: str, entities: list[dict], *,
                   source_file: str, chunk_index: int) -> str:
    rels = ", ".join(ALLOWED_RELATION_TYPES)
    entity_lines = "\n".join(
        f"  - {e['name']} :: {e['type']}" for e in entities
    ) or "  (no entities found in this chunk)"
    return (
        "Given these ENTITIES already extracted from TEXT, extract typed "
        "relations between them. Return JSON of the form:\n"
        "{\n"
        '  "relations": [\n'
        '    {"source": "<entity name>",\n'
        '     "target": "<entity name>",\n'
        '     "type": "<one of: ' + rels + '>",\n'
        '     "confidence": <float 0..1 reflecting how clearly TEXT supports it>,\n'
        '     "evidence_text": "<exact short span from TEXT>"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- source and target MUST be names from the ENTITIES list exactly.\n"
        "- type MUST be from the allowed list.\n"
        "- confidence should reflect TEXTUAL clarity, not your own belief.\n"
        "- evidence_text is a verbatim short span (<=200 chars) from TEXT.\n"
        "- Do NOT output relations the text does not support.\n"
        "- If nothing qualifies, return {\"relations\": []}.\n\n"
        f"SOURCE: {source_file}  CHUNK: {chunk_index}\n\n"
        f"ENTITIES:\n{entity_lines}\n\n"
        "TEXT:\n"
        "---\n"
        f"{text}\n"
        "---"
    )


VISION_SYSTEM = (
    "You read supply-chain charts and diagrams from screenshots. You "
    "respond with STRICT JSON only. You never invent values the image "
    "does not clearly show. You state a confidence between 0 and 1 that "
    "reflects how reliably the chart can be read, not how good the "
    "chart looks. Blurry labels, truncated axes, and missing legends "
    "lower confidence sharply."
)


def vision_user(*, source_file: str) -> str:
    return (
        "Describe the chart or diagram in the attached image. Return JSON "
        "of the form:\n"
        "{\n"
        '  "chart_type": "bar | line | scatter | pie | diagram | map | other",\n'
        '  "title": "<title as shown, or empty string>",\n'
        '  "x_axis_label": "<label text, or empty>",\n'
        '  "y_axis_label": "<label text, or empty>",\n'
        '  "x_tick_labels": ["<string>", ...],\n'
        '  "data_points": [\n'
        '    {"series": "<series name or empty>",\n'
        '     "x": "<x label>", "y": <numeric>}\n'
        "  ],\n"
        '  "entities_mentioned": ["<company / port / country / SKU as it '
        'appears in the chart>", ...],\n'
        '  "description": "<2-5 sentence prose summary of what the chart '
        'says. Do NOT speculate beyond the pixels.>",\n'
        '  "confidence": <float 0..1 reflecting read reliability>,\n'
        '  "notes": "<optional caveats: cropped axis, unlabelled bars, etc.>"\n'
        "}\n\n"
        "Rules:\n"
        "- Omit data_points you cannot read; it is better to return few\n"
        "  points than wrong ones.\n"
        "- 'y' must be numeric; drop points where you'd have to guess.\n"
        "- confidence <= 0.65 is normal for chart screenshots; the ingest\n"
        "  caps it there regardless.\n\n"
        f"SOURCE: {source_file}"
    )


VERIFIER_SYSTEM = (
    "You verify candidate supply-chain relations extracted by another "
    "model. You respond with STRICT JSON only. For each candidate you "
    "state whether the TEXT clearly supports it (accept), does not "
    "support it (reject), or supports a different type between the "
    "same two entities (modify). You never introduce new candidates."
)


def verifier_user(text: str, candidates: list[dict], *,
                   source_file: str, chunk_index: int) -> str:
    rels = ", ".join(ALLOWED_RELATION_TYPES)
    cand_lines = "\n".join(
        f"  {i+1}. {c['source']} --[{c['type']}]--> {c['target']}"
        f"  (proposer confidence: {c.get('confidence', '?')})"
        for i, c in enumerate(candidates)
    ) or "  (no candidates)"
    return (
        "For each CANDIDATE relation below, return a verdict based ONLY on "
        "the TEXT. Return JSON of the form:\n"
        "{\n"
        '  "verified": [\n'
        '    {"index": <1-based int>,\n'
        '     "source": "<entity>",\n'
        '     "target": "<entity>",\n'
        '     "type": "<unchanged, or new type if verdict=modify>",\n'
        '     "verdict": "accept" | "reject" | "modify",\n'
        '     "confidence": <float 0..1 after review>,\n'
        '     "note": "<short reason, verbatim-cited where possible>"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- One output entry per candidate; preserve order.\n"
        "- modify may ONLY change 'type', not source/target.\n"
        f"- type must be from the allowed list: {rels}.\n\n"
        f"SOURCE: {source_file}  CHUNK: {chunk_index}\n\n"
        f"CANDIDATES:\n{cand_lines}\n\n"
        "TEXT:\n"
        "---\n"
        f"{text}\n"
        "---"
    )
