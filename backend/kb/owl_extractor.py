"""Extract OWL-ish ontology elements (classes, methods, tables, columns, relations, roles)
from PHP source and SQL DDL/seed scripts."""
import re
from typing import Dict, List, Any


# ---------- PHP ----------
PHP_CLASS_RE = re.compile(r"class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:extends\s+([A-Za-z_][A-Za-z0-9_\\]*))?", re.MULTILINE)
PHP_NAMESPACE_RE = re.compile(r"namespace\s+([A-Za-z0-9_\\]+)\s*;")
PHP_METHOD_RE = re.compile(r"(public|private|protected)\s+function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", re.MULTILINE)
PHP_SESSION_RE = re.compile(r"session\(\)?->(?:get\(['\"]([^'\"]+)['\"]\)|userdata\(['\"]([^'\"]+)['\"]\))")
PHP_DB_TABLE_RE = re.compile(r"->(?:table|from|join|get|insert|update|delete)\(\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]")
PHP_ROUTE_RE = re.compile(r"\$routes->(?:get|post|put|delete|match)\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]")


def extract_php(content: str, filename: str = "") -> List[Dict[str, Any]]:
    """Returns list of entity dicts."""
    entities: List[Dict[str, Any]] = []
    namespace_match = PHP_NAMESPACE_RE.search(content)
    namespace = namespace_match.group(1) if namespace_match else ""

    # Routes
    for m in PHP_ROUTE_RE.finditer(content):
        entities.append({
            "type": "ROUTE",
            "name": m.group(1),
            "handler": m.group(2),
            "source": filename,
        })

    # Classes
    for cls_match in PHP_CLASS_RE.finditer(content):
        cls_name = cls_match.group(1)
        extends = cls_match.group(2) or ""
        cls_start = cls_match.start()
        # find matching brace block
        brace_start = content.find("{", cls_start)
        if brace_start < 0:
            continue
        # naive: take until end of file
        cls_body = content[brace_start:]

        methods: List[Dict[str, Any]] = []
        for mm in PHP_METHOD_RE.finditer(cls_body):
            method_name = mm.group(2)
            params = mm.group(3).strip()
            # scan ~600 chars after method start for session/db refs
            mstart = mm.start()
            window = cls_body[mstart:mstart + 1500]
            sessions = set()
            tables = set()
            for sm in PHP_SESSION_RE.finditer(window):
                sessions.add(sm.group(1) or sm.group(2))
            for tm in PHP_DB_TABLE_RE.finditer(window):
                tables.add(tm.group(1))
            methods.append({
                "name": method_name,
                "params": params,
                "sessions": sorted([s for s in sessions if s]),
                "tables": sorted(tables),
            })

        # Sessions across the class
        sess_all = set()
        for sm in PHP_SESSION_RE.finditer(cls_body):
            sess_all.add(sm.group(1) or sm.group(2))

        entities.append({
            "type": "CLASS",
            "name": cls_name,
            "namespace": namespace,
            "extends": extends,
            "methods": methods,
            "session_fields": sorted([s for s in sess_all if s]),
            "source": filename,
        })

    return entities


# ---------- SQL ----------
SQL_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\((.*?)\)\s*(?:ENGINE|;)",
    re.IGNORECASE | re.DOTALL,
)
SQL_PK_RE = re.compile(r"PRIMARY\s+KEY\s*\(\s*[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\)", re.IGNORECASE)
SQL_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\(\s*[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\)\s*REFERENCES\s+[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\(\s*[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?",
    re.IGNORECASE,
)
SQL_COLUMN_RE = re.compile(
    r"^\s*[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s+([a-zA-Z]+(?:\([^)]*\))?)",
    re.MULTILINE,
)
SQL_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?\s*\([^)]*\)\s*VALUES\s*(.+?);",
    re.IGNORECASE | re.DOTALL,
)


def extract_sql(content: str, filename: str = "") -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []

    for tbl_match in SQL_CREATE_TABLE_RE.finditer(content):
        table_name = tbl_match.group(1)
        body = tbl_match.group(2)

        # PK
        pk_match = SQL_PK_RE.search(body)
        pk = pk_match.group(1) if pk_match else ""

        # FKs
        fks = []
        for fkm in SQL_FK_RE.finditer(body):
            fks.append({
                "column": fkm.group(1),
                "ref_table": fkm.group(2),
                "ref_column": fkm.group(3),
            })

        # Columns: parse line-by-line
        columns = []
        seen = set()
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            up = line.upper()
            if up.startswith(("PRIMARY", "KEY", "INDEX", "UNIQUE", "FOREIGN", "CONSTRAINT")):
                continue
            cm = SQL_COLUMN_RE.match(line)
            if cm:
                col_name = cm.group(1)
                col_type = cm.group(2)
                if col_name.upper() in ("PRIMARY", "KEY", "INDEX", "UNIQUE", "FOREIGN", "CONSTRAINT"):
                    continue
                if col_name in seen:
                    continue
                seen.add(col_name)
                columns.append({"name": col_name, "type": col_type})

        entities.append({
            "type": "TABLE",
            "name": table_name,
            "pk": pk,
            "columns": columns,
            "fks": fks,
            "source": filename,
        })

    # INSERT statements — extract roles / lookup individuals from common tables
    for ins in SQL_INSERT_RE.finditer(content):
        tbl = ins.group(1)
        vals = ins.group(2)
        if any(k in tbl.lower() for k in ["role", "stage", "circle", "agency"]):
            # Pull quoted strings
            names = re.findall(r"'([^']{2,80})'", vals)
            for nm in set(names):
                if not nm.replace("-", "").replace("_", "").replace(" ", "").isdigit() and len(nm) > 1:
                    entities.append({
                        "type": "INDIVIDUAL",
                        "name": nm,
                        "category": tbl,
                        "source": filename,
                    })

    return entities


def extract_zip(content: str, filename: str = "") -> List[Dict[str, Any]]:
    """ZIP content is concatenated as `===== FILE: path =====` blocks.
    Split it and route each block to the right extractor based on the inner filename's extension."""
    entities: List[Dict[str, Any]] = []
    # split on the marker; each piece is "path =====\n<body>"
    parts = content.split("===== FILE:")
    for part in parts:
        if not part.strip():
            continue
        # part starts with " <path> =====\n<body>"
        try:
            header, body = part.split("=====", 1)
        except ValueError:
            continue
        inner_name = header.strip()
        lname = inner_name.lower()
        src = f"{filename}::{inner_name}" if filename else inner_name
        if lname.endswith(".php"):
            entities.extend(extract_php(body, src))
        elif lname.endswith(".sql"):
            entities.extend(extract_sql(body, src))
    return entities


def extract(filetype: str, content: str, filename: str = "") -> List[Dict[str, Any]]:
    if filetype == "php":
        return extract_php(content, filename)
    if filetype == "sql":
        return extract_sql(content, filename)
    if filetype == "zip":
        return extract_zip(content, filename)
    return []


def aggregate_stats(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = {
        "entities": len(entities),
        "classes": 0,
        "methods": 0,
        "tables": 0,
        "columns": 0,
        "roles": 0,
        "relationships": 0,
        "routes": 0,
    }
    for e in entities:
        t = e.get("type")
        if t == "CLASS":
            stats["classes"] += 1
            stats["methods"] += len(e.get("methods", []))
        elif t == "TABLE":
            stats["tables"] += 1
            stats["columns"] += len(e.get("columns", []))
            stats["relationships"] += len(e.get("fks", []))
        elif t == "INDIVIDUAL":
            if "role" in (e.get("category") or "").lower():
                stats["roles"] += 1
        elif t == "ROUTE":
            stats["routes"] += 1
    stats["modules"] = len([e for e in entities if e.get("type") == "MODULE"])
    stats["component_maps"] = len([e for e in entities if e.get("type") == "COMPONENT_MAP"])
    return stats
