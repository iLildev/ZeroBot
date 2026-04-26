"""Tests for the event publisher's HMAC signing helpers."""

from zerobot.events.publisher import (
    SIGNATURE_SCHEME,
    compute_signature,
    verify_signature,
)


def test_signature_format_is_sha256_hex():
    """A signature is always ``sha256=<64-hex-chars>``."""
    sig = compute_signature("secret", b'{"event":"ping"}')
    scheme, _, hex_digest = sig.partition("=")
    assert scheme == SIGNATURE_SCHEME
    assert len(hex_digest) == 64
    assert all(c in "0123456789abcdef" for c in hex_digest)


def test_verify_accepts_correct_signature():
    """A signature produced by ``compute_signature`` round-trips."""
    body = b'{"event":"wallet_topup","payload":{"amount":5}}'
    sig = compute_signature("secret", body)
    assert verify_signature("secret", body, sig) is True


def test_verify_rejects_tampered_body():
    """Modifying a single byte must invalidate the signature."""
    body = b'{"event":"wallet_topup","payload":{"amount":5}}'
    sig = compute_signature("secret", body)
    tampered = body.replace(b"5", b"9")
    assert verify_signature("secret", tampered, sig) is False


def test_verify_rejects_wrong_secret():
    """A signature from secret A must not validate under secret B."""
    body = b"hi"
    sig = compute_signature("secret-A", body)
    assert verify_signature("secret-B", body, sig) is False


def test_verify_rejects_missing_or_empty_inputs():
    """Missing secret, missing header, or wrong scheme all fail safely."""
    body = b"hi"
    sig = compute_signature("secret", body)
    assert verify_signature("", body, sig) is False
    assert verify_signature("secret", body, None) is False
    assert verify_signature("secret", body, "") is False
    assert verify_signature("secret", body, "md5=deadbeef") is False
