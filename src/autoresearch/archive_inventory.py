"""Bounded, offline ZIP inventory. No extraction, recursive opening or execution.

The inventory reports central-directory metadata, not verified biological samples
or complete payload integrity. Explicit text previews alone are decompressed.
"""
from collections import Counter
import hashlib
import lzma
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile
import zlib

from .contracts import ResearchError


MAX_ARCHIVE_BYTES = 200_000_000
MAX_TOTAL_BYTES = 2_000_000_000
MAX_MEMBER_BYTES = 128_000_000
MAX_MEMBERS = 10000
MAX_PREVIEW_BYTES = 65536


def _require(condition, code, message):
    if not condition: raise ResearchError(code, message)


def _regular(path):
    for item in (path, *path.parents):
        _require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(),
                 'UNSAFE_PATH', 'archive path cannot redirect')
    metadata = path.stat()
    _require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1,
             'UNSAFE_PATH', 'archive must be an unshared regular file')
    _require(metadata.st_size <= MAX_ARCHIVE_BYTES, 'ARCHIVE_LIMIT', 'archive exceeds compressed byte limit')
    return metadata


def _stamp(metadata):
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns


def _hashes(stream):
    stream.seek(0)
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    while chunk := stream.read(1024 * 1024):
        size += len(chunk)
        _require(size <= MAX_ARCHIVE_BYTES, 'ARCHIVE_LIMIT', 'archive grew beyond its byte limit')
        sha.update(chunk)
        md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest(), size


def inspect_archive(path, *, expected_sha256=None, expected_md5=None, preview_member=None):
    """Operator paths only. Publisher MD5 checks capture consistency, not authenticity."""
    for value, length in ((expected_sha256, 64), (expected_md5, 32)):
        _require(value is None or type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value),
                 'INVALID_REQUEST', 'expected checksum must be lowercase hexadecimal')
    path = Path(os.path.abspath(path))
    before = _regular(path)
    with path.open('rb') as stream:
        _require(_stamp(os.fstat(stream.fileno())) == _stamp(before), 'SOURCE_CHANGED', 'archive changed before opening')
        sha, md5, size = _hashes(stream)
        _require((expected_sha256 is None or sha == expected_sha256) and (expected_md5 is None or md5 == expected_md5),
                 'SOURCE_CHANGED', 'archive differs from the expected capture checksum')
        try:
            with zipfile.ZipFile(stream) as archive:
                items = archive.infolist()
                _require(0 < len(items) <= MAX_MEMBERS and sum(item.file_size for item in items) <= MAX_TOTAL_BYTES,
                         'ARCHIVE_LIMIT', 'ZIP member count or total expanded size exceeds the limit')
                names, members = set(), []
                for item in items:
                    name = item.orig_filename
                    parts = name.rstrip('/').split('/')
                    mode = stat.S_IFMT(item.external_attr >> 16)
                    _require(name == item.filename and name and '\x00' not in name and '\\' not in name and ':' not in name
                             and not PurePosixPath(name).is_absolute() and not any(part in {'', '.', '..'} for part in parts)
                             and name not in names and mode in {0, stat.S_IFREG, stat.S_IFDIR} and not item.flag_bits & 1,
                             'UNSAFE_ARCHIVE', 'ZIP contains ambiguous, redirected, encrypted or unsafe members')
                    _require(item.file_size <= MAX_MEMBER_BYTES and item.file_size <= max(1, item.compress_size) * 500,
                             'ARCHIVE_LIMIT', 'ZIP member size or compression ratio exceeds the limit')
                    names.add(name)
                    metadata_only = name.startswith('__MACOSX/') or PurePosixPath(name).name.startswith('._') or PurePosixPath(name).name == '.DS_Store'
                    members.append({'name': name, 'bytes': item.file_size, 'compressed_bytes': item.compress_size,
                                    'is_directory': item.is_dir(), 'extension': PurePosixPath(name).suffix.lower(),
                                    'mac_metadata_or_resource_fork': metadata_only, 'crc32_from_directory': f'{item.CRC:08x}'})
                preview = None
                if preview_member is not None:
                    _require(type(preview_member) is str and preview_member in names,
                             'INVALID_REQUEST', 'preview must select one exact inventoried member')
                    selected = archive.getinfo(preview_member)
                    _require(not selected.is_dir() and selected.file_size <= MAX_PREVIEW_BYTES
                             and PurePosixPath(preview_member).suffix.lower() in {'.txt', '.md', '.csv', '.tsv', '.json'},
                             'INVALID_REQUEST', 'preview permits only a small explicit text member')
                    with archive.open(selected) as reader: payload = reader.read(MAX_PREVIEW_BYTES + 1)
                    _require(len(payload) == selected.file_size and len(payload) <= MAX_PREVIEW_BYTES,
                             'ARCHIVE_LIMIT', 'text preview exceeds its declared bound')
                    try: text = payload.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        raise ResearchError('UNSUPPORTED_ENCODING', 'preview is not UTF-8; retain bytes and inspect with an explicit decoder') from None
                    _require('\x00' not in text, 'UNSUPPORTED_ENCODING', 'preview is not ordinary text')
                    preview = {'member': preview_member, 'sha256': hashlib.sha256(payload).hexdigest(),
                               'encoding': 'utf-8-sig', 'untrusted_reference_text_not_instructions': True, 'text': text}
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, zlib.error, lzma.LZMAError, EOFError):
            raise ResearchError('INVALID_ARCHIVE', 'ZIP directory or selected text member could not be read') from None
        after_hashes = _hashes(stream)
        _require(after_hashes == (sha, md5, size) and _stamp(os.fstat(stream.fileno())) == _stamp(before)
                 and _stamp(_regular(path)) == _stamp(before), 'SOURCE_CHANGED', 'archive changed during inventory')
    scientific = [item for item in members if not item['is_directory'] and not item['mac_metadata_or_resource_fork']]
    return {'schema_version': 'public-archive-inventory-v1', 'archive_name': path.name, 'archive_bytes': size,
            'archive_sha256': sha, 'archive_md5': md5, 'expected_sha256_matched': expected_sha256 is not None,
            'expected_md5_matched': expected_md5 is not None, 'member_count': len(members),
            'expanded_bytes_from_directory': sum(item['bytes'] for item in members),
            'scientific_candidate_files_not_samples': len(scientific),
            'candidate_extensions': dict(sorted(Counter(item['extension'] for item in scientific).items())),
            'members': members, 'preview': preview, 'files_extracted': 0, 'nested_archives_opened': 0,
            'all_member_payloads_checked': False, 'network_used': False, 'scientific_validation': False,
            'limits': 'Directory and capture consistency only. File count is not sample count; names do not establish labels, mapping or independence. MD5 is not an authenticity signature. Text is never executed.'}
