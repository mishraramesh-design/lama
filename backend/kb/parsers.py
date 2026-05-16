"""File parsers: extract text from PHP / SQL / PDF / DOCX / CSV / TXT."""
import io
import csv
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


def parse_file(filename: str, content: bytes) -> tuple[str, str]:
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
