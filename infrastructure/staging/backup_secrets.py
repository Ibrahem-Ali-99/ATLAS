"""Secure local storage for the backup passphrase.

Windows uses the current user's DPAPI profile. Linux deployments continue to
use the root-only environment file documented in recovery.md.
"""

from __future__ import annotations

import ctypes
import os
import secrets
import sys
from pathlib import Path
from typing import Final

STORE_NAME: Final = "atlas-backup-passphrase.dpapi"


class SecretStoreError(RuntimeError):
    pass


def store_path() -> Path:
    if sys.platform != "win32":
        raise SecretStoreError("windows_dpapi_unavailable")
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise SecretStoreError("localappdata_unavailable")
    return Path(root) / "ATLAS" / STORE_NAME


def initialize() -> Path:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SecretStoreError("passphrase_store_exists")
    passphrase = secrets.token_hex(32).encode("ascii")
    sealed = _protect(passphrase)
    with path.open("xb") as handle:
        handle.write(b"ATLAS-DPAPI-1\n" + sealed)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def retrieve() -> str:
    path = store_path()
    try:
        payload = path.read_bytes()
        if not payload.startswith(b"ATLAS-DPAPI-1\n"):
            raise SecretStoreError("passphrase_store_corrupt")
        value = _unprotect(payload.split(b"\n", 1)[1]).decode("ascii")
    except SecretStoreError:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SecretStoreError("passphrase_store_unavailable") from exc
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise SecretStoreError("passphrase_store_corrupt")
    return value


def resolve() -> str:
    configured = os.environ.get("ATLAS_BACKUP_PASSPHRASE", "")
    if configured:
        return configured
    if sys.platform != "win32":
        return ""
    return retrieve()


def _protect(value: bytes) -> bytes:
    return _crypt(value, protect=True)


def _unprotect(value: bytes) -> bytes:
    return _crypt(value, protect=False)


def _crypt(value: bytes, *, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise SecretStoreError("windows_dpapi_unavailable")
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    input_blob = Blob(len(value), source)
    output_blob = Blob()
    crypt = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    crypt.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_wchar_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(Blob),
    ]
    crypt.restype = ctypes.c_int
    if not crypt(
        ctypes.byref(input_blob),
        "ATLAS backup passphrase",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        raise SecretStoreError("dpapi_operation_failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)
