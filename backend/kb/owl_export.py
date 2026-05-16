"""OWL ontology export — JSON-LD style ontology of the legacy KB.

Computes:
  - classes, tables, routes, roles  (@graph)
  - data_model_hints (high-risk tables, audit/lookup/junction classification, domain map)
  - microservice_hints (suggested service boundaries by domain prefix)
  - migration_context (project meta + KB stats + SRS purpose summary)

Heuristic only — deterministic given the same input entities."""
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
from collections import defaultdict


def export_owl(
    project: Dict,
    entities: List[Dict],
    srs_sections: Dict[str, str] = None
) -> Dict:
    classes  = [e for e in entities if e.get("type") == "CLASS"]
    tables   = [e for e in entities if e.get("type") == "TABLE"]
    routes   = [e for e in entities if e.get("type") == "ROUTE"]
    indivs   = [e for e in entities if e.get("type") == "INDIVIDUAL"]

    # FK in-degree for risk scoring
    fk_in_degree: Dict[str, int] = {}
    for t in tables:
        for fk in (t.get("fks") or []):
            ref = fk.get("ref_table", "")
            fk_in_degree[ref] = fk_in_degree.get(ref, 0) + 1

    # Table classification
    audit_tables    = [t["name"] for t in tables
                       if t["name"].startswith("logs_")
                       or "audit" in t["name"].lower()]
    lookup_tables   = [t["name"] for t in tables
                       if len(t.get("columns") or []) <= 4
                       and len(t.get("fks") or []) == 0]
    junction_tables = [t["name"] for t in tables
                       if len(t.get("fks") or []) >= 2
                       and len(t.get("columns") or []) <= 5]
    high_risk_tables = sorted(
        [(t["name"],
          fk_in_degree.get(t["name"], 0) * 3
          + len(t.get("columns") or []) // 10
          + len(t.get("fks") or []) * 2)
         for t in tables],
        key=lambda x: x[1], reverse=True
    )[:20]

    # Domain grouping
    domain_map: Dict[str, Dict] = defaultdict(
        lambda: {"tables": [], "classes": []})
    for t in tables:
        parts  = t["name"].split("_")
        domain = parts[0] if len(parts) > 1 else "core"
        domain_map[domain]["tables"].append(t["name"])
    for c in classes:
        touched = set()
        for m in (c.get("methods") or []):
            for tbl in (m.get("tables") or []):
                parts = tbl.split("_")
                if len(parts) > 1:
                    touched.add(parts[0])
        for domain in (touched or {"core"}):
            domain_map[domain]["classes"].append(c["name"])

    # Suggested microservice boundaries
    suggested_boundaries = []
    for domain, content in domain_map.items():
        if domain in ("logs", "") or len(content["tables"]) < 2:
            continue
        suggested_boundaries.append({
            "service_name": f"{domain}-service",
            "tables":  content["tables"][:20],
            "classes": list(set(content["classes"]))[:10],
            "reason": (
                f"Domain prefix '{domain}' groups "
                f"{len(content['tables'])} tables and "
                f"{len(content['classes'])} controller classes "
                "with shared data access patterns."
            )
        })

    return {
        "@context": {
            "owl":  "http://www.w3.org/2002/07/owl#",
            "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "lama": "http://lama.migration/ontology#",
            "xsd":  "http://www.w3.org/2001/XMLSchema#"
        },
        "@graph": {
            "classes": [
                {
                    "@type":            "lama:ControllerClass",
                    "@id":              f"lama:{c['name']}",
                    "rdfs:label":       c["name"],
                    "lama:namespace":   c.get("namespace", ""),
                    "lama:extends":     c.get("extends", ""),
                    "lama:methods": [
                        {
                            "name":             m["name"],
                            "tables_accessed":  m.get("tables", []),
                            "session_vars":     m.get("sessions", []),
                        }
                        for m in (c.get("methods") or [])
                    ],
                    "lama:session_fields": c.get("session_fields", []),
                    "lama:source_file":    c.get("source", "")
                }
                for c in classes
            ],
            "tables": [
                {
                    "@type":           "lama:DatabaseTable",
                    "@id":             f"lama:{t['name']}",
                    "rdfs:label":      t["name"],
                    "lama:primaryKey": t.get("pk", ""),
                    "lama:columns": [
                        {
                            "name":  c["name"],
                            "type":  c["type"],
                            "isPK":  c["name"] == t.get("pk", ""),
                            "isFK":  any(fk["column"] == c["name"]
                                         for fk in t.get("fks", []))
                        }
                        for c in (t.get("columns") or [])
                    ],
                    "lama:foreignKeys": [
                        {
                            "column":     fk["column"],
                            "references": fk["ref_table"],
                            "type":       "lama:ForeignKeyRelation"
                        }
                        for fk in (t.get("fks") or [])
                    ],
                    "lama:riskScore": (
                        fk_in_degree.get(t["name"], 0) * 3
                        + len(t.get("columns") or []) // 10
                        + len(t.get("fks") or []) * 2
                    ),
                    "lama:isAuditTable":    t["name"] in audit_tables,
                    "lama:isLookupTable":   t["name"] in lookup_tables,
                    "lama:isJunctionTable": t["name"] in junction_tables,
                }
                for t in tables
            ],
            "routes": [
                {
                    "@type":         "lama:HttpRoute",
                    "@id":           f"lama:route_{i}",
                    "lama:path":     r.get("name", ""),
                    "lama:handler":  r.get("handler", ""),
                    "lama:source":   r.get("source", "")
                }
                for i, r in enumerate(routes)
            ],
            "roles": [
                {
                    "@type":          "lama:UserRole",
                    "rdfs:label":     ind.get("name", ""),
                    "lama:category":  ind.get("category", "")
                }
                for ind in indivs
            ]
        },
        "migration_context": {
            "project":      project.get("name", ""),
            "source_tech":  project.get("source_tech", ""),
            "target_tech":  project.get("target_tech", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": {
                "classes":    len(classes),
                "tables":     len(tables),
                "routes":     len(routes),
                "roles":      len(indivs),
                "total_fks":  sum(len(t.get("fks") or []) for t in tables)
            },
            "srs_summary": (srs_sections or {}).get("purpose", "")[:500]
        },
        "data_model_hints": {
            "high_risk_tables":  [{"table": n, "score": s}
                                   for n, s in high_risk_tables],
            "audit_tables":      audit_tables,
            "lookup_tables":     lookup_tables[:30],
            "junction_tables":   junction_tables,
            "domains":           dict(domain_map),
        },
        "microservice_hints": {
            "suggested_boundaries":    suggested_boundaries,
            "total_suggested_services": len(suggested_boundaries),
            "rationale": (
                "Boundaries derived from table prefix grouping "
                "and class-to-table access patterns in the KB."
            )
        }
    }
