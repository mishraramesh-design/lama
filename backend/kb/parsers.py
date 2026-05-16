"""File parsers: extract text from PHP / SQL / PDF / DOCX / CSV / TXT / ZIP."""
import io
import csv
import zipfile
from typing import Optional


def parse_php(content: bytes) -> str:
    return content.decode("utf-8", errors="ignore")


def parse_sql(content: bytes) -> str:
    return content.decode("utf-8", errors="ignore")


def parse_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="ignore")


def parse_csv(content: bytes) -> str:
    text = content.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader):
        rows.append(" | ".join(row))
        if i > 5000:
            break
    return "\n".join(rows)


def parse_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception as e:
        return f"[PDF parse error: {e}]"


def parse_docx(content: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        return f"[DOCX parse error: {e}]"


def parse_zip(content: bytes) -> str:
    """Extract a .zip in memory and concatenate text from all supported members."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except Exception as e:
        return f"[ZIP open error: {e}]"

    parts: list[str] = []
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        # skip junk + nested zips (avoid recursion bombs)
        lower = name.lower()
        if any(skip in lower for skip in ["__macosx", ".ds_store", "node_modules/", ".git/", "vendor/", "__pycache__/"]):
            continue
        if lower.endswith(".zip"):
            continue
        try:
            data = zf.read(name)
        except Exception:
            continue
        # recurse via parse_file but avoid re-zip
        _ftype, text = parse_file(name, data, allow_zip_recurse=False)
        if text.strip():
            parts.append(f"\n===== FILE: {name} =====\n{text}")
    return "\n".join(parts)


def parse_file(filename: str, content: bytes, allow_zip_recurse: bool = True) -> tuple[str, str]:
    """Returns (filetype, extracted_text)."""
    name = filename.lower()
    if name.endswith(".php"):
        return "php", parse_php(content)
    if name.endswith(".sql"):
        return "sql", parse_sql(content)
    if name.endswith(".pdf"):
        return "pdf", parse_pdf(content)
    if name.endswith(".docx"):
        return "docx", parse_docx(content)
    if name.endswith(".csv"):
        return "csv", parse_csv(content)
    if name.endswith((".txt", ".md")):
        return "txt", parse_txt(content)
    if name.endswith(".zip") and allow_zip_recurse:
        return "zip", parse_zip(content)
    # Default: treat as text
    return "txt", parse_txt(content)


def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 150) -> list[str]:
    """Simple character-based chunker with overlap."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        # try to cut on newline
        if end < n:
            nl = text.rfind("\n", start, end)
            if nl > start + chunk_size // 2:
                end = nl
        chunks.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
