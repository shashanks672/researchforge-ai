"""Bounded parser subprocess. No OCR, macros, links, or embedded files are executed."""

import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID, uuid5


@dataclass
class Page:
    text: str
    page: int | None
    heading: str | None = None


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "\n".join(
        re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines() if line.strip()
    ).translate(dict.fromkeys([*range(0, 9), 11, 12, *range(14, 32), 127]))


def parse(path: Path, suffix: str) -> list[Page]:
    pages: list[Page] = []
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path, strict=True)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("pdf_limits")
        for number, page in enumerate(reader.pages, 1):
            # Compressed streams are still parsed in a disposable, deadline-bound process.
            stream = page.get_contents()
            if stream is not None and len(stream.get_data()) > 5_000_000:
                raise ValueError("pdf_limits")
            pages.append(Page(clean(page.extract_text() or ""), number))
        if not any(p.text.strip() for p in pages):
            raise ValueError("ocr_required")
    elif suffix == ".docx":
        from docx import Document

        with zipfile.ZipFile(path) as archive:
            if (
                len(archive.infolist()) > 500
                or sum(i.file_size for i in archive.infolist()) > 20_000_000
            ):
                raise ValueError("archive_limits")
            if any(i.flag_bits & 1 for i in archive.infolist()):
                raise ValueError("archive_limits")
            if "word/document.xml" not in archive.namelist():
                raise ValueError("invalid_document")
        doc = Document(str(path))
        heading = None
        for block in doc.iter_inner_content():
            if hasattr(block, "rows"):
                text = "\n".join(" | ".join(c.text for c in row.cells) for row in block.rows)
            else:
                text = block.text
                if block.style and block.style.name.startswith("Heading"):
                    heading = clean(text)[:300]
            pages.append(Page(clean(text), None, heading))
    else:
        raw = path.read_bytes()
        if b"\0" in raw:
            raise ValueError("invalid_document")
        text = clean(raw.decode("utf-8-sig", errors="strict"))
        heading = None
        for section in re.split(r"(?m)(?=^#{1,6} )", text):
            if section.startswith("#"):
                heading = section.splitlines()[0].lstrip("# ")[:300]
            pages.append(Page(section, None, heading))
    if not any(p.text.strip() for p in pages):
        raise ValueError("empty_document")
    if sum(len(p.text) for p in pages) > 250_000:
        raise ValueError("extraction_limit")
    return [p for p in pages if p.text.strip()]


def chunks(
    pages: list[Page], document_id: UUID, size: int, overlap: int
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[int | None, str]] = set()
    for page in pages:
        start = 0
        while start < len(page.text):
            end = min(start + size, len(page.text))
            if end < len(page.text):
                boundary = page.text.rfind(" ", start + size // 2, end)
                if boundary > start:
                    end = boundary
            text = page.text[start:end].strip()
            digest = hashlib.sha256(text.encode()).hexdigest()
            if text and (page.page, digest) not in seen:
                seen.add((page.page, digest))
                result.append(
                    {
                        "id": str(uuid5(document_id, f"chars-v1:{page.page}:{start}:{digest}")),
                        "ordinal": len(result),
                        "page": page.page,
                        "heading": page.heading,
                        "text": text,
                        "checksum": digest,
                    }
                )
            if end == len(page.text):
                break
            start = max(start + 1, end - overlap)
    if len(result) > 400:
        raise ValueError("chunk_limit")
    return result


def main() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    # macOS does not reliably enforce RLIMIT_AS/RSS; input/decompression limits and
    # process termination reduce exposure but are not a hostile-file sandbox.
    try:
        pages = parse(Path(sys.argv[1]), sys.argv[2])
        print(json.dumps({"pages": [asdict(p) for p in pages]}))
    except Exception as exc:
        code = (
            str(exc)
            if str(exc)
            in {
                "ocr_required",
                "empty_document",
                "archive_limits",
                "extraction_limit",
                "pdf_limits",
            }
            else "invalid_document"
        )
        print(json.dumps({"error": code}))


if __name__ == "__main__":
    main()
