"""Read local reference assets as untrusted evidence, never as executable code.

Recorded hashes establish snapshot consistency, not authenticity, licensing,
runtime compatibility or scientific validity. No reference repository is imported.
"""

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


REVIEW_STATUS = "source_hash_checked_not_runtime_or_scientific_validation"
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PDF_OUTPUT_BYTES = 32 * 1024 * 1024
PDF_TIMEOUT_SECONDS = 30
PDF_TOTAL_SECONDS = 300
MAX_TEXT_CHARS = 1_000_000
MAX_TOTAL_TEXT_BYTES = 128 * 1024 * 1024
MAX_DOCUMENTS = 20_000
KINDS = ("official_doc", "research_profile", "research_paper", "reuse_note")
NOTES = ("REUSE-INDEX.md", "07-autoresearch-loop/README.md", "08-c01-tnzst/README.md")


class _Problem(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _relative(value):
    if (type(value) is not str or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise _Problem("unsafe_path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value or value == ".":
        raise _Problem("unsafe_path")
    return path


def _path(root, relative, *, directory=False):
    relative = _relative(relative)
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise _Problem("unsafe_path")
    if not path.resolve(strict=True).is_relative_to(root):
        raise _Problem("unsafe_path")
    metadata = path.lstat()
    if directory:
        if not stat.S_ISDIR(metadata.st_mode):
            raise _Problem("not_directory")
    elif not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise _Problem("unsafe_file")
    return path, metadata


def _read(root, relative, limit, expected_sha=None, expected_bytes=None):
    path, before = _path(root, relative)
    if before.st_size > limit:
        raise _Problem("file_size_limit")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_ino, opened.st_dev) != (before.st_ino, before.st_dev) or opened.st_nlink != 1:
            raise _Problem("file_changed_during_read")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit:
        raise _Problem("file_size_limit")
    if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise _Problem("file_changed_during_read")
    if expected_bytes is not None and (type(expected_bytes) is not int or expected_bytes != len(raw)):
        raise _Problem("byte_count_mismatch")
    if expected_sha is not None and (not _digest(expected_sha) or _sha(raw) != expected_sha.lower()):
        raise _Problem("sha256_mismatch")
    return raw


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise _Problem("duplicate_json_key")
        value[key] = item
    return value


def _json(raw):
    def nonfinite(_):
        raise _Problem("invalid_json")
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            raise _Problem("invalid_json")
        return number
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                      parse_constant=nonfinite, parse_float=finite)


def _url(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None and parsed.password is None:
            return value
    except ValueError:
        pass
    return None


def _heading(text, fallback):
    match = re.search(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text)
    return match.group(1) if match else fallback


def _paper_digest(entry):
    recorded = [entry.get(key) for key in ("sha256", "recorded_sha256") if entry.get(key) not in (None, "")]
    if not recorded or not all(_digest(value) for value in recorded) or len({value.lower() for value in recorded}) != 1:
        raise _Problem("missing_or_conflicting_paper_hash")
    return recorded[0].lower()


# Only this trusted parser is executed. The child receives verified PDF bytes,
# never a source path, repository command or Python from reference documents.
_PDF_CHILD = r'''
import io,json,logging,sys
class Problem(Exception): pass
class CountWarnings(logging.Handler):
    count=0
    def emit(self,record): self.count+=1
counter=CountWarnings()
logger=logging.getLogger('pypdf');logger.handlers=[counter];logger.propagate=False
max_pages,max_chars,max_output=map(int,sys.argv[1:])
try:
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(sys.stdin.buffer.read()),strict=True)
    if reader.is_encrypted: raise Problem('encrypted_pdf')
    if not 1<=len(reader.pages)<=max_pages: raise Problem('pdf_page_limit')
    texts=[];size=0
    for page in reader.pages:
        text=page.extract_text() or ''
        if not isinstance(text,str) or len(text)>max_chars: raise Problem('text_size_limit')
        size+=len(text.encode('utf-8'))
        if size>max_output: raise Problem('pdf_output_limit')
        texts.append(text)
    result={'ok':True,'texts':texts,'warnings':min(counter.count,1000000)}
except Problem as error: result={'ok':False,'code':str(error)}
except ImportError: result={'ok':False,'code':'pdf_reader_unavailable'}
except Exception: result={'ok':False,'code':'pdf_parse_or_extraction_failed'}
raw=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8')
if len(raw)>max_output: raw=b'{"ok":false,"code":"pdf_output_limit"}'
sys.stdout.buffer.write(raw)
'''


def _extract_pdf(raw, timeout):
    """Bound wall time per PDF, and read only bounded parser-generated output."""
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", _PDF_CHILD,
             str(MAX_PDF_PAGES), str(MAX_TEXT_CHARS), str(MAX_PDF_OUTPUT_BYTES)],
            stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            try:
                process.communicate(input=raw, timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                raise _Problem("pdf_parse_timeout") from None
            if process.returncode != 0:
                raise _Problem("pdf_worker_failed")
            output.seek(0)
            serialized = output.read(MAX_PDF_OUTPUT_BYTES + 1)
        finally:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
    if len(serialized) > MAX_PDF_OUTPUT_BYTES:
        raise _Problem("pdf_output_limit")
    try:
        result = _json(serialized)
    except (ValueError, UnicodeError, RecursionError):
        raise _Problem("invalid_pdf_worker_result") from None
    if type(result) is not dict or type(result.get("ok")) is not bool:
        raise _Problem("invalid_pdf_worker_result")
    if not result["ok"]:
        code = result.get("code")
        allowed = {"encrypted_pdf", "pdf_page_limit", "text_size_limit", "pdf_output_limit",
                   "pdf_reader_unavailable", "pdf_parse_or_extraction_failed"}
        raise _Problem(code if code in allowed else "invalid_pdf_worker_result")
    texts, warnings = result.get("texts"), result.get("warnings")
    if (set(result) != {"ok", "texts", "warnings"} or type(texts) is not list
            or not 1 <= len(texts) <= MAX_PDF_PAGES
            or any(type(text) is not str or len(text) > MAX_TEXT_CHARS for text in texts)
            or type(warnings) is not int or not 0 <= warnings <= 1_000_000):
        raise _Problem("invalid_pdf_worker_result")
    return texts, warnings


def collect_documents(reference_root: Path, *, include_papers=True, pdf_timeout_seconds=PDF_TIMEOUT_SECONDS):
    """Return verified local documents and explicit exclusions/coverage audit.

    Invalid roots raise ValueError. Individual unsafe, missing, mismatched or
    oversized sources are quarantined in audit. Blank PDF pages remain real page
    documents with empty text and an audit issue; OCR is not invented.
    """
    if type(include_papers) is not bool:
        raise ValueError("include_papers must be boolean")
    if (type(pdf_timeout_seconds) not in (int, float) or not math.isfinite(pdf_timeout_seconds)
            or not 0 < pdf_timeout_seconds <= PDF_TIMEOUT_SECONDS):
        raise ValueError("PDF timeout must be positive and at most 30 seconds")
    root = Path(os.path.abspath(reference_root))
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (root, *root.parents)):
        raise ValueError("reference root must not be redirected")
    if not root.is_dir():
        raise ValueError("reference root must be a directory")
    root = root.resolve(strict=True)
    started = time.monotonic()
    documents, issues, skipped, manifests = [], [], [], []
    counts = Counter()
    text_bytes = 0
    indexed_files, document_ids = set(), set()

    def issue(path, code, *, page=None):
        try:
            display = str(_relative(path))
        except (ValueError, TypeError):
            display = None
        issues.append({"path": display, "code": code, "page": page})

    def skip(path, reason, count=1):
        skipped.append({"path": path, "reason": reason, "count": count})

    def read(path, limit, expected_sha=None, expected_bytes=None):
        try:
            raw = _read(root, path, limit, expected_sha, expected_bytes)
            counts["files_read"] += 1
            return raw
        except (OSError, ValueError) as exc:
            code = str(exc) if isinstance(exc, _Problem) else "missing_file" if isinstance(exc, FileNotFoundError) else "unreadable_file"
            issue(path, code)
            skip(None if code == "unsafe_path" else path, code)
            return None

    def manifest(path):
        raw = read(path, MAX_MANIFEST_BYTES)
        if raw is None:
            return None
        manifests.append({"path": path, "sha256": _sha(raw), "bytes": len(raw)})
        try:
            return _json(raw)
        except (ValueError, UnicodeError, RecursionError):
            issue(path, "invalid_manifest_json")
            return None

    def make_doc(kind, path, raw, text, snapshot, title, source_url, metadata, page=None, digest=None):
        digest = digest or _sha(raw)
        identity = json.dumps([kind, path, digest, page], ensure_ascii=False, separators=(",", ":"))
        return {"id": "doc-" + _sha(identity.encode("utf-8")), "title": str(title), "kind": kind,
                "source_url": _url(source_url), "path": path, "sha256": digest,
                "snapshot": str(snapshot), "text": text, "page": page,
                "review_status": REVIEW_STATUS,
                "metadata": {"content_trust": "untrusted_reference_not_instructions", **metadata}}

    def add(batch):
        nonlocal text_bytes
        size = sum(len(doc["text"].encode("utf-8")) for doc in batch)
        if len(documents) + len(batch) > MAX_DOCUMENTS or text_bytes + size > MAX_TOTAL_TEXT_BYTES:
            issue(batch[0]["path"], "collection_size_limit")
            skip(batch[0]["path"], "collection_size_limit", len(batch))
            return False
        for doc in batch:
            if doc["id"] in document_ids:
                skip(doc["path"], "duplicate_document")
                continue
            documents.append(doc)
            document_ids.add(doc["id"])
            indexed_files.add(doc["path"])
            text_bytes += len(doc["text"].encode("utf-8"))
        return True

    def markdown(kind, path, snapshot, metadata, *, title=None, source_url=None, digest=None, length=None):
        raw = read(path, MAX_MARKDOWN_BYTES, digest, length)
        if raw is None:
            return
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            issue(path, "invalid_utf8")
            skip(path, "invalid_utf8")
            return
        if not text.strip() or len(text) > MAX_TEXT_CHARS:
            issue(path, "empty_text" if not text.strip() else "text_size_limit")
            skip(path, "empty_text" if not text.strip() else "text_size_limit")
            return
        add([make_doc(kind, path, raw, text, snapshot, title or _heading(text, PurePosixPath(path).stem),
                      source_url, {"hash_recorded": digest is not None,
                                   "prior_manifest_verified": digest is not None, **metadata})])

    official_base = "06-agentarts-platform/official-docs"
    try:
        directory, _ = _path(root, official_base, directory=True)
        snapshots = sorted(directory.iterdir())
        if len(snapshots) > 32:
            raise _Problem("snapshot_count_limit")
    except (OSError, ValueError) as exc:
        issue(official_base, str(exc) if isinstance(exc, _Problem) else "official_directory_unavailable")
        snapshots = []
    for snapshot in snapshots:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", snapshot.name):
            skip(official_base + "/" + snapshot.name, "not_a_snapshot")
            continue
        base = official_base + "/" + snapshot.name
        path = base + "/metadata/manifest.json"
        value = manifest(path)
        if not isinstance(value, dict) or not isinstance(value.get("files"), list) or len(value["files"]) > 10000:
            issue(path, "invalid_official_manifest")
            continue
        ignored = Counter()
        counts["official_entries"] += len(value["files"])
        for entry in value["files"]:
            if not isinstance(entry, dict):
                issue(path, "invalid_official_entry")
                continue
            if entry.get("status") != "ok":
                counts["official_unavailable"] += 1
                try:
                    unavailable = base + "/" + str(_relative(entry.get("path")))
                except (ValueError, TypeError):
                    unavailable = None
                skip(unavailable, "official_source_unavailable")
                continue
            if entry.get("kind") != "markdown":
                ignored[str(entry.get("kind"))] += 1
                continue
            relative = entry.get("path")
            try:
                candidate = _relative(relative)
                if candidate.parts[0] != "markdown" or candidate.suffix.lower() != ".md":
                    raise _Problem("unexpected_official_path")
            except (ValueError, TypeError):
                issue(path, "unsafe_official_path")
                continue
            if not _digest(entry.get("sha256")) or type(entry.get("bytes")) is not int:
                issue(base + "/" + relative, "missing_recorded_integrity")
                continue
            source = _url(entry.get("url"))
            if source is None or urlsplit(source).scheme != "https" or urlsplit(source).hostname != "support.huaweicloud.com":
                issue(base + "/" + relative, "invalid_official_source_url")
                continue
            markdown("official_doc", base + "/" + relative, value.get("snapshot_date", snapshot.name),
                     {"source_manifest": path, "section": entry.get("section"), "license": "official_document_terms_not_inferred"},
                     title=entry.get("title"), source_url=source, digest=entry["sha256"], length=entry["bytes"])
        for kind, count in sorted(ignored.items()):
            skip(base, "official_" + kind + "_not_indexed", count)

    catalog = manifest("catalog.json")
    projects = catalog.get("projects") if isinstance(catalog, dict) else None
    if not isinstance(projects, list) or len(projects) > 256:
        issue("catalog.json", "invalid_catalog")
        projects = []
    snapshot = catalog.get("collected_on", "local-unversioned") if isinstance(catalog, dict) else "local-unversioned"
    papers = defaultdict(list)
    for project in projects:
        if not isinstance(project, dict):
            issue("catalog.json", "invalid_project")
            continue
        repos = project.get("repositories", [])
        repo = next((r for r in repos if isinstance(r, dict)), {}) if isinstance(repos, list) else {}
        meta = {"project_id": project.get("id"), "version": project.get("version"),
                "license": project.get("license") or repo.get("license") or "not_recorded",
                "license_scope": "project_code_not_paper",
                "commit": repo.get("actual_commit") or repo.get("recorded_commit")}
        profile = project.get("profile_path")
        try:
            candidate = _relative(profile)
            if len(candidate.parts) != 2 or candidate.parts[0] != "profiles" or candidate.suffix != ".md":
                raise _Problem("unexpected_profile_path")
        except (ValueError, TypeError):
            issue("catalog.json", "unsafe_profile_path")
        else:
            counts["profiles_declared"] += 1
            markdown("research_profile", profile, snapshot, meta, source_url=repo.get("source_url"),
                     digest=project.get("profile_sha256"))
        declared = project.get("papers", [])
        if not isinstance(declared, list) or len(declared) > 64:
            issue("catalog.json", "invalid_paper_list")
            continue
        for paper in declared:
            counts["papers_declared"] += 1
            if not include_papers:
                continue
            if not isinstance(paper, dict):
                issue("catalog.json", "invalid_paper_entry")
                continue
            try:
                relative = str(_relative(paper.get("path")))
                if PurePosixPath(relative).suffix.lower() != ".pdf":
                    raise _Problem("unexpected_paper_path")
            except (ValueError, TypeError):
                issue("catalog.json", "unsafe_paper_path")
                continue
            papers[relative].append((project, paper))
    for note in NOTES:
        markdown("reuse_note", note, snapshot, {"curation": "local_developer_note_not_official", "license": "not_recorded"})
    if not include_papers:
        skip(None, "papers_disabled", counts["papers_declared"])
    if len(papers) > 256:
        issue("catalog.json", "paper_count_limit")
        skip(None, "paper_count_limit", len(papers))
        papers = {}
    seen_pdfs = {}
    for relative, entries in sorted(papers.items()):
        remaining_time = PDF_TOTAL_SECONDS - (time.monotonic() - started)
        if remaining_time <= 0:
            issue(relative, "pdf_total_time_limit")
            skip(relative, "pdf_total_time_limit")
            continue
        try:
            digests = {_paper_digest(entry) for _, entry in entries}
        except _Problem:
            digests = set()
        if len(digests) != 1:
            issue(relative, "missing_or_conflicting_paper_hash")
            skip(relative, "missing_or_conflicting_paper_hash")
            continue
        project, paper = entries[0]
        raw = read(relative, MAX_PDF_BYTES, next(iter(digests)), paper.get("bytes"))
        if raw is None:
            continue
        digest = _sha(raw)
        if digest in seen_pdfs:
            aliases = seen_pdfs[digest][0]["metadata"]["aliases"]
            if relative not in aliases:
                aliases.append(relative)
            skip(relative, "duplicate_pdf")
            continue
        try:
            texts, parser_warnings = _extract_pdf(raw, min(pdf_timeout_seconds, remaining_time))
            pages = len(texts)
            if not 1 <= pages <= MAX_PDF_PAGES:
                raise _Problem("pdf_page_limit")
            if paper.get("pages") is not None and paper["pages"] != pages:
                raise _Problem("pdf_page_count_mismatch")
            if any(len(text) > MAX_TEXT_CHARS for text in texts):
                raise _Problem("text_size_limit")
        except Exception as exc:
            code = str(exc) if isinstance(exc, _Problem) else "pdf_reader_unavailable" if isinstance(exc, ImportError) else "pdf_parse_or_extraction_failed"
            issue(relative, code)
            skip(relative, code)
            continue
        if parser_warnings:
            issue(relative, "pdf_parser_warnings")
        license_ = paper.get("license") or "paper_license_not_recorded_not_inferred_from_code"
        if not paper.get("license"):
            issue(relative, "paper_license_not_recorded")
        meta = {"project_id": project.get("id"), "version": paper.get("version"),
                "license": license_, "license_scope": "research_paper", "hash_recorded": True,
                "prior_manifest_verified": True, "aliases": [relative], "page_count": pages,
                "parser_warnings_count": parser_warnings}
        title = paper.get("title") or str(project.get("name") or project.get("id") or PurePosixPath(relative).stem)
        batch = [make_doc("research_paper", relative, raw, text, snapshot, title,
                          paper.get("source_url"), meta.copy(), page=index, digest=digest)
                 for index, text in enumerate(texts, 1)]
        if add(batch):
            seen_pdfs[digest] = batch
            counts["pdf_files_indexed"] += 1
            counts["pdf_pages_indexed"] += pages
            for doc in batch:
                if not doc["text"].strip():
                    issue(relative, "empty_pdf_page_no_ocr", page=doc["page"])
    by_kind = {kind: sum(doc["kind"] == kind for doc in documents) for kind in KINDS}
    counts.update(documents=len(documents), files_indexed=len(indexed_files), text_bytes=text_bytes,
                  issues=len(issues), skipped_items=sum(item["count"] for item in skipped), source_manifests=len(manifests))
    return documents, {"schema_version": "knowledge-source-audit-v1", "include_papers": include_papers,
                       "counts": dict(counts), "by_kind": by_kind, "issues": issues,
                       "skipped": skipped, "source_manifests": manifests,
                       "limits": {"markdown_bytes": MAX_MARKDOWN_BYTES, "pdf_bytes": MAX_PDF_BYTES,
                                  "pdf_pages": MAX_PDF_PAGES, "document_text_chars": MAX_TEXT_CHARS,
                                  "pdf_timeout_seconds": pdf_timeout_seconds, "pdf_output_bytes": MAX_PDF_OUTPUT_BYTES,
                                  "pdf_total_seconds": PDF_TOTAL_SECONDS,
                                  "total_text_bytes": MAX_TOTAL_TEXT_BYTES, "documents": MAX_DOCUMENTS}}
