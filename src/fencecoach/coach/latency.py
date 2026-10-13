"""Small reply budgets and representative evidence for routine chat turns."""

import json
import re

from fencecoach.coach.intent import wants_all_reps as _wants_all_reps
from fencecoach.coach.intent import wants_rep_comparison as _wants_rep_comparison


def compact_session_context(snapshot: str) -> str:
    """Share definitions, column schemas and reference metadata without dropping facts."""
    packet = json.loads(snapshot)
    definitions, definition_ids, schemas, schema_ids, references, reference_ids = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    text_counts = {}

    def count(value):
        if isinstance(value, str) and len(value) >= 80:
            text_counts[value] = text_counts.get(value, 0) + 1
        elif isinstance(value, dict):
            for item in value.values():
                count(item)
        elif isinstance(value, list):
            for item in value:
                count(item)

    count(packet)

    def schema(columns):
        key = tuple(columns)
        if key not in schema_ids:
            identifier = f"columns_{len(schemas) + 1}"
            schema_ids[key] = identifier
            schemas[identifier] = list(columns)
        return schema_ids[key]

    def definition(text):
        if text not in definition_ids:
            identifier = f"note_{len(definitions) + 1}"
            definition_ids[text] = identifier
            definitions[identifier] = text
        return definition_ids[text]

    def tables(records):
        groups = []
        for record in records:
            identifier = schema(list(record))
            if not groups or groups[-1]["schema_ref"] != identifier:
                groups.append({"schema_ref": identifier, "rows": []})
            groups[-1]["rows"].append(list(record.values()))
        return groups

    def intern(value):
        if isinstance(value, str) and text_counts.get(value, 0) > 1:
            return {"text_ref": definition(value)}
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "meaning" and isinstance(item, str) and item:
                    result["meaning_ref"] = definition(item)
                    continue
                processed = intern(item)
                if (
                    key
                    in {
                        "reference_comparisons",
                        "per_rep_reference_findings",
                        "local_record_groups",
                    }
                    and isinstance(processed, list)
                    and all(isinstance(record, dict) for record in processed)
                ):
                    result[key] = {"record_tables": tables(processed)}
                elif (
                    key in {"measures", "phases", "drill_benchmarks"}
                    and isinstance(processed, dict)
                    and all(isinstance(record, dict) for record in processed.values())
                ):
                    result[key] = {
                        "keyed_record_tables": tables(
                            [{"record_key": name, **record} for name, record in processed.items()]
                        )
                    }
                elif key in {"values", "units", "ranges"} and isinstance(processed, dict):
                    result[key] = {
                        "keyed_values": {
                            "schema_ref": schema(list(processed)),
                            "row": list(processed.values()),
                        }
                    }
                elif key == "columns" and isinstance(processed, list):
                    result[key] = {"column_schema_ref": schema(processed)}
                elif key == "field_schemas" and isinstance(processed, dict):
                    result[key] = {
                        name: {"column_schema_ref": schema(columns)}
                        for name, columns in processed.items()
                    }
                elif key == "reference_context" and isinstance(processed, dict):
                    serialized = json.dumps(processed, separators=(",", ":"))
                    if serialized not in reference_ids:
                        identifier = f"reference_{len(references) + 1}"
                        reference_ids[serialized] = identifier
                        references[identifier] = processed
                    result[key] = {"reference_context_ref": reference_ids[serialized]}
                else:
                    result[key] = processed
            return result
        if isinstance(value, list):
            return [intern(item) for item in value]
        return value

    compact = intern(packet)
    compact["measurement_definitions"] = definitions
    compact["record_schemas"] = schemas
    compact["reference_contexts"] = references
    compact["encoding"] = (
        "Read table rows using columns from record_schemas[schema_ref]. keyed_record_tables "
        "use record_key as the original dictionary key; keyed_values pair the schema's keys "
        "with row values. Resolve meaning_ref/text_ref using measurement_definitions and "
        "reference_context_ref using reference_contexts. column_schema_ref denotes the "
        "named list in record_schemas. All original records are retained."
    )
    return json.dumps(compact, separators=(",", ":"))


def expand_session_context(snapshot: str) -> dict:
    """Reconstruct the canonical packet for losslessness checks and diagnostics."""
    packet = json.loads(snapshot)
    definitions = packet.pop("measurement_definitions", {})
    schemas = packet.pop("record_schemas", {})
    references = packet.pop("reference_contexts", {})
    packet.pop("encoding", None)

    def columns(table):
        return table["columns"] if "columns" in table else schemas[table["schema_ref"]]

    def expand(value):
        if isinstance(value, dict):
            if set(value) == {"text_ref"}:
                return definitions[value["text_ref"]]
            if set(value) == {"reference_context_ref"}:
                return expand(references[value["reference_context_ref"]])
            if set(value) == {"column_schema_ref"}:
                return schemas[value["column_schema_ref"]]
            if "keyed_values" in value:
                table = value["keyed_values"]
                return {
                    key: expand(item)
                    for key, item in zip(columns(table), table["row"], strict=True)
                }
            if "record_tables" in value or "keyed_record_tables" in value:
                keyed = "keyed_record_tables" in value
                records = [
                    expand(dict(zip(columns(table), row, strict=True)))
                    for table in value.get("record_tables", value.get("keyed_record_tables", []))
                    for row in table["rows"]
                ]
                if keyed:
                    return {
                        record.pop(
                            "record_key" if "record_key" in record else "measurement_name"
                        ): record
                        for record in records
                    }
                return records
            return {
                "meaning" if key == "meaning_ref" else key: definitions[item]
                if key == "meaning_ref"
                else expand(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    return expand(packet)


def local_session_context(snapshot: str) -> str:
    """Lossless provider-neutral evidence encoding for detailed records and diagnostics."""
    return compact_session_context(snapshot)


def local_overview_context(snapshot: str) -> str:
    """Small-model inventory; exact requested records remain available through tools.

    Present every rep and feature without preloading all detailed phase/reference
    rows. The agent chooses which exact records it needs from their meanings.
    """
    packet = json.loads(snapshot)
    names = list(
        dict.fromkeys(
            name
            for rep in packet.get("per_rep_measurements", [])
            for name in rep.get("measures", {})
        )
    )
    definitions, phase_inventory, reps = {}, {}, []
    for rep in packet.get("per_rep_measurements", []):
        overrides = {}
        for name, record in rep["measures"].items():
            definition = {
                "unit": record.get("unit"),
                "phase": record.get("phase"),
                "meaning": record.get("meaning"),
            }
            definitions.setdefault(name, definition)
            if definitions[name] != definition:
                overrides[name] = definition
        for name, phase in rep["phases"].items():
            available = phase_inventory.setdefault(name, {})
            available.update(phase.get("units", {}))
        reps.append(
            {
                "rep": rep["rep"],
                "finish_seconds": rep.get("finish_seconds"),
                "values": [rep["measures"].get(name, {}).get("value") for name in names],
                "definition_overrides": overrides,
                "phases": {
                    name: {
                        "interval_seconds": phase["interval_seconds"],
                        "samples": phase.get("samples"),
                    }
                    for name, phase in rep["phases"].items()
                },
                "reference_context": rep.get("reference_context", {}),
                "reference_comparisons_available": len(rep.get("reference_comparisons", [])),
                "benchmark_names_available": list(rep.get("drill_benchmarks", {})),
                "review_checks": rep.get("review_checks", []),
            }
        )
    overview = {
        **{key: value for key, value in packet.items() if key != "per_rep_measurements"},
        "measure_columns": names,
        "measure_definitions": definitions,
        "phase_features_available": phase_inventory,
        "per_rep_measurements": reps,
        "detail_access": "Every rep, primary measurement and available phase/feature is indexed here. For phase analysis, benchmark details, or comparison with approved examples, fetch exact records using get_technique_evaluation(feature_names, phase_names, rep_numbers), compare_to_baseline(metric_name, phase, rep_number), or inspect_reviewed_rep(rep_number). Omitted phase/reference rows are AVAILABLE through these tools, not missing evidence. Get the relevant records before drawing that conclusion. Choose names by the athlete's meaning, not question categories.",
    }
    return compact_session_context(json.dumps(overview, separators=(",", ":")))


def wants_all_reps(question: str) -> bool:
    return _wants_all_reps(question)


def wants_rep_comparison(question: str) -> bool:
    """Whether the athlete is asking us to rank or compare the attempts."""
    return _wants_rep_comparison(question)


def wants_detail(question: str) -> bool:
    return bool(
        re.search(
            r"\b(detailed?|thorough|comprehensive)\b|in depth|step[ -]by[ -]step|all (?:reps|measurements)",
            question,
            re.I,
        )
        or wants_all_reps(question)
    )


def compact_measurements(rows, question, profile, focus_id=None, limit=6, preferred_ids=()):
    """Keep actual source IDs and extrema; never invent an aggregate measurement."""
    question = question.lower()
    if "arm" in question or "hand" in question:
        terms, side = ("arm_extension", "elbow_angle"), profile.get("weapon_arm")
    elif "knee" in question or "leg" in question:
        terms, side = ("knee_angle", "knee_flexion"), profile.get("front_leg")
    elif "recover" in question or "return" in question:
        terms, side = ("recovery",), None
    else:
        terms, side = ("knee_angle", "arm_extension", "elbow_angle", "torso_tilt"), None
    focused = [r for r in rows if r["metric_id"] == focus_id]
    relevant = [r for r in rows if any(t in r["name"] for t in terms)]
    if side in {"left", "right"}:
        relevant = [
            r
            for r in relevant
            if not r["name"].startswith(("left_", "right_")) or r["name"].startswith(side + "_")
        ]
    relevant = relevant or rows
    relevant = sorted(relevant, key=lambda r: r["metric_id"] not in preferred_ids)
    groups = {}
    for row in relevant:
        groups.setdefault(row["name"], []).append(row)
    selected = list(focused)
    for group in groups.values():
        ordered = sorted(group, key=lambda r: r["value"])
        for row in (ordered[0], ordered[-1]):
            if row not in selected:
                selected.append(row)
    return [
        {
            k: r[k]
            for k in ("metric_id", "name", "value", "unit", "confidence", "start_ms", "end_ms")
            if k in r
        }
        for r in selected[:limit]
    ]


def compact_guidance(text, limit=650):
    """Keep complete leading sentences rather than cutting a recommendation halfway."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    ends = list(re.finditer(r"[.!?](?=\s|$)", head))
    return head[: ends[-1].end()] if ends else head.rsplit("\n", 1)[0]
