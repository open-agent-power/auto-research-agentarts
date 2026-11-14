"""Read the one existing study review capsule; never rebuild or execute it."""
import hashlib
import os
from pathlib import Path
import stat

_CAPSULE = Path('/workspace/auto-research-agentarts/runs/sprint-016-study-capsule-20261114/study-review-capsule.zip')
_SIZE = 4671421
_SHA256 = '3c12efc995a4a4e4e61763150b1d5de818755dbbdf6e892c15d43c9c96a0c598'
_FILENAME = 'study-review-capsule.zip'
_SCHEMA = 'saved-study-capsule-v1'


class _CapsuleFailure(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read_verified():
    try:
        for part in (_CAPSULE, *_CAPSULE.parents):
            if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
                raise _CapsuleFailure('integrity_error', 'A fixed capsule path redirects through a link.')
        fd = os.open(_CAPSULE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != _SIZE:
                raise _CapsuleFailure('integrity_error', 'The fixed capsule is not the expected bounded regular file.')
            raw = stream.read(_SIZE + 1)
            after = os.fstat(stream.fileno())
        try:
            current = _CAPSULE.stat(follow_symlinks=False)
        except OSError:
            raise _CapsuleFailure('unknown', 'The capsule changed during reading.') from None
        if _identity(before) != _identity(after) or _identity(after) != _identity(current):
            raise _CapsuleFailure('unknown', 'The capsule changed during reading.')
        if len(raw) != _SIZE or hashlib.sha256(raw).hexdigest() != _SHA256:
            raise _CapsuleFailure('integrity_error', 'The capsule bytes do not match the saved identity.')
        return raw
    except _CapsuleFailure:
        raise
    except FileNotFoundError:
        raise _CapsuleFailure('unavailable', 'The original capsule is missing.') from None
    except OSError:
        raise _CapsuleFailure('unavailable', 'The original capsule cannot be read.') from None


def _result(error=None):
    result = {'schema_version': _SCHEMA, 'status': error.status if error else 'available',
              'filename': _FILENAME, 'expected_bytes': _SIZE, 'expected_sha256': _SHA256,
              'study_id': 'g5-scheduling-threshold-transfer-v1', 'source_commit': '62f09edbf15f90cdcd08450aab5d60199d44d63f',
              'scope': 'saved_standalone_study_review_capsule_not_current_product_environment', 'may_execute': False,
              'notice': 'Saved review evidence and original study code; not a complete environment, source authentication or scientific validation.'}
    if error:
        result['reason'] = str(error)
    return result


def describe_capsule():
    """Check the complete fixed bytes before reporting whether they are available."""
    try:
        _read_verified()
        return _result()
    except _CapsuleFailure as error:
        return _result(error)


def read_capsule():
    """Return the verified bytes or an explicit error; no second file open for sending."""
    try:
        raw = _read_verified()
        return _result(), raw
    except _CapsuleFailure as error:
        return _result(error), None
