import hashlib

from im_guard_ml.auth import parse_auth_config


def test_parse_auth_config_keeps_legacy_token_as_admin():
    config = parse_auth_config("legacy", "")

    assert config.enabled is True
    assert config.role_for_token("legacy") == "admin"
    assert config.allows("admin", "audit") is True


def test_parse_auth_config_supports_role_tokens():
    config = parse_auth_config("", "write-token:writer,read-token:reader,audit-token:auditor")

    assert config.allows(config.role_for_token("write-token"), "write") is True
    assert config.allows(config.role_for_token("write-token"), "audit") is False
    assert config.allows(config.role_for_token("read-token"), "read") is True
    assert config.allows(config.role_for_token("audit-token"), "audit") is True


def test_parse_auth_config_supports_sha256_token_hashes():
    token_hash = hashlib.sha256("hashed-secret".encode("utf-8")).hexdigest()
    config = parse_auth_config("", "", f"{token_hash}:writer")

    assert config.enabled is True
    assert config.role_for_token("hashed-secret") == "writer"
    assert config.role_for_token("wrong-secret") is None
    assert config.allows(config.role_for_token("hashed-secret"), "write") is True
    assert config.allows(config.role_for_token("hashed-secret"), "audit") is False
