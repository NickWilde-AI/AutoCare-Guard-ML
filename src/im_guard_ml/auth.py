from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


ROLE_PERMISSIONS = {
    "admin": {"read", "write", "audit", "config"},
    "writer": {"write"},
    "reader": {"read", "config"},
    "auditor": {"read", "audit"},
}


@dataclass(frozen=True)
class AuthConfig:
    token_roles: dict[str, str]
    token_hash_roles: dict[str, str]

    @property
    def enabled(self) -> bool:
        return bool(self.token_roles or self.token_hash_roles)

    def role_for_token(self, token: str) -> str | None:
        for expected, role in self.token_roles.items():
            if hmac.compare_digest(token, expected):
                return role
        if self.token_hash_roles and token:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            for expected_hash, role in self.token_hash_roles.items():
                if hmac.compare_digest(digest, expected_hash.lower()):
                    return role
        return None

    def allows(self, role: str | None, permission: str) -> bool:
        if role is None:
            return not self.enabled
        return permission in ROLE_PERMISSIONS.get(role, set())


def parse_auth_config(single_token: str = "", token_spec: str = "", token_hash_spec: str = "") -> AuthConfig:
    token_roles: dict[str, str] = {}
    token_hash_roles: dict[str, str] = {}
    if single_token:
        token_roles[single_token] = "admin"
    for item in token_spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            token, role = item.split(":", 1)
        else:
            token, role = item, "admin"
        token = token.strip()
        role = role.strip() or "admin"
        if token:
            token_roles[token] = role
    for item in token_hash_spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            token_hash, role = item.split(":", 1)
        else:
            token_hash, role = item, "admin"
        token_hash = token_hash.strip().lower()
        role = role.strip() or "admin"
        if _is_sha256_hex(token_hash):
            token_hash_roles[token_hash] = role
    return AuthConfig(token_roles, token_hash_roles)


def _is_sha256_hex(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value.lower())
