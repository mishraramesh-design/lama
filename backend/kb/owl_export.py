"""OWL ontology export — domain hints, high-risk entity ranking,
suggested microservice boundaries — consumed by the pipeline context
handoff at the SRS freeze point.

Heuristic only — no LLM. Deterministic given the same input entities."""
from collections import defaultdict
from typing import Dict, List, Any


def _table_domain(name: str) -> str:
    """First underscore-segment is the domain prefix (e.g. abp_claim → 'abp')."""
    if not name:
        return "other"
    parts = name.split("_")
    return parts[0] if len(parts) > 1 else "other"


def _class_domain(name: str) -> str:
    """Class domain = first prefix segment when present, else 'other'."""
    if not name:
        return "other"
    # split on underscore or camel boundary
    for sep in ("_", "-"):
        if sep in name:
            return name.split(sep)[0].lower()
    # heuristic: first 3 chars
    return name[:3].lower() if len(name) >= 3 else name.lower()


def export_owl(project: Dict[str, Any], entities: List[Dict[str, Any]], srs_sections: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Build a JSON-LD-ish OWL export.

    Returns a dict with:
      classes, tables, individuals, routes,
      data_model_hints: { domains, high_risk_tables },
      microservice_hints: { suggested_boundaries }
    """
    classes = [e for e in entities if e.get("type") == "CLASS"]
    tables = [e for e in entities if e.get("type") == "TABLE"]
    routes = [e for e in entities if e.get("type") == "ROUTE"]
    individuals = [e for e in entities if e.get("type") == "INDIVIDUAL"]

    # Group tables and classes by domain prefix
    domains: Dict[str, Dict[str, list]] = defaultdict(lambda: {"tables": [], "classes": []})
    for t in tables:
        domains[_table_domain(t.get("name", ""))]["tables"].append(t.get("name", ""))
    for c in classes:
        domains[_class_domain(c.get("name", ""))]["classes"].append(c.get("name", ""))

    # High-risk tables: ranked by FK count + column count
    def _risk(t: dict) -> int:
        return len(t.get("fks") or []) * 3 + len(t.get("columns") or [])

    ranked = sorted(tables, key=_risk, reverse=True)
    high_risk_tables = [
        {
            "name": t.get("name"),
            "fk_count": len(t.get("fks") or []),
            "column_count": len(t.get("columns") or []),
            "risk_score": _risk(t),
            "reason": (
                "many FK dependencies" if len(t.get("fks") or []) >= 3
                else "wide table" if len(t.get("columns") or []) >= 20
                else "moderate complexity"
            ),
        }
        for t in ranked[:25]
    ]

    # Suggested microservice boundaries: one per domain with > N tables/classes
    suggested_boundaries = []
    for d, content in sorted(domains.items(), key=lambda kv: -(len(kv[1]["tables"]) + len(kv[1]["classes"]))):
        size = len(content["tables"]) + len(content["classes"])
        if size < 3:
            continue
        suggested_boundaries.append({
            "name": d,
            "tables": content["tables"][:20],
            "classes": list(set(content["classes"]))[:10],
            "size": size,
            "rationale": f"Cohesive domain '{d}' with {len(content['tables'])} tables and {len(set(content['classes']))} classes",
        })

    return {
        "@context": "https://lama.local/owl/v1",
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "source_tech": project.get("source_tech"),
            "target_tech": project.get("target_tech"),
        },
        "counts": {
            "classes": len(classes),
            "tables": len(tables),
            "routes": len(routes),
            "individuals": len(individuals),
        },
        "data_model_hints": {
            "domains": {k: v for k, v in domains.items()},
            "high_risk_tables": high_risk_tables,
        },
        "microservice_hints": {
            "suggested_boundaries": suggested_boundaries[:12],
        },
    }
