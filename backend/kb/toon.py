"""TOON (Typed Object Oriented Notation) serialiser.

Format example:
  [CLASS:CCA_approval] pkg=App.Controllers extends=BaseController
    [METHOD:cca_fls_calculation] auth=session(admin_detail) role=cca db=pmis_projects
    [SESSION:admin_detail] fields=user_id,user_agency,role_id
  [TABLE:pmis_projects] pk=project_id
    [COL:scheme_id] type=int fk->pmis_schemes
    [COL:project_type] type=varchar
"""
from typing import List, Dict, Any


def _csv(values):
    return ",".join(str(v) for v in values if v not in (None, ""))


def serialise_class(entity: Dict[str, Any]) -> str:
    name = entity.get("name", "Unknown")
    ns = entity.get("namespace") or ""
    extends = entity.get("extends") or ""
    line = f"[CLASS:{name}]"
    if ns:
        line += f" pkg={ns}"
    if extends:
        line += f" extends={extends}"
    lines = [line]

    sess_fields = entity.get("session_fields") or []
    if sess_fields:
        lines.append(f"  [SESSION:admin_detail] fields={_csv(sess_fields)}")

    for m in entity.get("methods", []) or []:
        parts = [f"  [METHOD:{m['name']}]"]
        if m.get("sessions"):
            parts.append(f"auth=session({_csv(m['sessions'])})")
        if m.get("tables"):
            parts.append(f"db={_csv(m['tables'])}")
        lines.append(" ".join(parts))

    return "\n".join(lines)


def serialise_table(entity: Dict[str, Any]) -> str:
    name = entity.get("name", "Unknown")
    pk = entity.get("pk", "")
    line = f"[TABLE:{name}]"
    if pk:
        line += f" pk={pk}"
    lines = [line]

    fk_map = {fk["column"]: fk for fk in entity.get("fks", [])}

    for col in entity.get("columns", []) or []:
        cname = col["name"]
        ctype = col["type"]
        part = f"  [COL:{cname}] type={ctype}"
        if cname in fk_map:
            part += f" fk->{fk_map[cname]['ref_table']}"
        lines.append(part)

    return "\n".join(lines)


def serialise_route(entity: Dict[str, Any]) -> str:
    return f"[ROUTE:{entity.get('name')}] handler={entity.get('handler','')}"


def serialise_individual(entity: Dict[str, Any]) -> str:
    return f"[INDIVIDUAL:{entity.get('name')}] in={entity.get('category','')}"


def serialise(entities: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []

    classes = [e for e in entities if e.get("type") == "CLASS"]
    tables = [e for e in entities if e.get("type") == "TABLE"]
    routes = [e for e in entities if e.get("type") == "ROUTE"]
    individuals = [e for e in entities if e.get("type") == "INDIVIDUAL"]

    if classes:
        blocks.append("# CLASSES")
        blocks.extend(serialise_class(c) for c in classes)
    if tables:
        blocks.append("\n# TABLES")
        blocks.extend(serialise_table(t) for t in tables)
    if routes:
        blocks.append("\n# ROUTES")
        blocks.extend(serialise_route(r) for r in routes)
    if individuals:
        blocks.append("\n# INDIVIDUALS")
        # group by category
        by_cat: Dict[str, List[str]] = {}
        for ind in individuals:
            by_cat.setdefault(ind.get("category", "misc"), []).append(ind.get("name", ""))
        for cat, names in by_cat.items():
            blocks.append(f"[GROUP:{cat}] members={','.join(sorted(set(names)))}")

    return "\n".join(blocks)


def summarise(entities: List[Dict[str, Any]], stats: Dict[str, int]) -> str:
    """Short textual summary of the KB for system prompts."""
    parts = [
        f"Entities: {stats.get('entities', 0)} total",
        f"{stats.get('classes', 0)} PHP classes",
        f"{stats.get('methods', 0)} methods",
        f"{stats.get('tables', 0)} DB tables",
        f"{stats.get('columns', 0)} columns",
        f"{stats.get('relationships', 0)} foreign keys",
        f"{stats.get('roles', 0)} roles",
        f"{stats.get('routes', 0)} routes",
    ]
    return ", ".join(parts)
