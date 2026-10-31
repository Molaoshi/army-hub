"""Minimal native macOS Keychain integration without command-line secrets."""
from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_char_p, c_int32, c_uint32, c_void_p, string_at


class NativeKeychainError(RuntimeError):
    pass


_SECURITY = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
_CORE = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_SECURITY.SecKeychainAddGenericPassword.argtypes = [c_void_p, c_uint32, c_char_p, c_uint32, c_char_p, c_uint32, c_void_p, c_void_p]
_SECURITY.SecKeychainAddGenericPassword.restype = c_int32
_SECURITY.SecKeychainFindGenericPassword.argtypes = [c_void_p, c_uint32, c_char_p, c_uint32, c_char_p, POINTER(c_uint32), POINTER(c_void_p), c_void_p]
_SECURITY.SecKeychainFindGenericPassword.restype = c_int32
_SECURITY.SecKeychainItemDelete.argtypes = [c_void_p]
_SECURITY.SecKeychainItemDelete.restype = c_int32
_SECURITY.SecKeychainItemFreeContent.argtypes = [c_void_p, c_void_p]
_SECURITY.SecKeychainItemFreeContent.restype = c_int32
_CORE.CFRelease.argtypes = [c_void_p]


def _check(status: int, operation: str) -> None:
    if status != 0:
        raise NativeKeychainError(f"Keychain {operation} failed with OSStatus {status}")


def add_secret(service: str, account: str, secret: str) -> None:
    service_bytes = service.encode()
    account_bytes = account.encode()
    secret_bytes = secret.encode()
    _check(_SECURITY.SecKeychainAddGenericPassword(
        None, len(service_bytes), service_bytes, len(account_bytes), account_bytes,
        len(secret_bytes), secret_bytes, None,
    ), "add")


def find_item(service: str, account: str, with_secret: bool) -> tuple[c_void_p, bytes | None]:
    service_bytes = service.encode()
    account_bytes = account.encode()
    length = c_uint32()
    data = c_void_p()
    item = c_void_p()
    status = _SECURITY.SecKeychainFindGenericPassword(
        None, len(service_bytes), service_bytes, len(account_bytes), account_bytes,
        byref(length) if with_secret else None, byref(data) if with_secret else None, byref(item),
    )
    _check(status, "lookup")
    secret = string_at(data, length.value) if with_secret and data.value else None
    if data.value:
        _SECURITY.SecKeychainItemFreeContent(None, data)
    return item, secret


def get_secret(service: str, account: str) -> str:
    item, secret = find_item(service, account, True)
    _CORE.CFRelease(item)
    return (secret or b"").decode()


def delete_secret(service: str, account: str) -> None:
    item, _ = find_item(service, account, False)
    try:
        _check(_SECURITY.SecKeychainItemDelete(item), "delete")
    finally:
        _CORE.CFRelease(item)
