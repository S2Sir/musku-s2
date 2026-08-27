"""test_auth_verify.py — Firebase ID-token verification + spoof protection."""
import base64
import json
import time
import unittest

import auth_verify as av


def _b64url(b: bytes) -> str:
    return base64.b64encode(b).decode().replace("+", "-").replace("/", "_").rstrip("=")


def _make_token(priv, uid, aud=av.PROJECT_ID, iss=av.ISSUER, exp_offset=3600, kid="testkey", tamper=False):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": iss, "aud": aud, "exp": now + exp_offset, "uid": uid, "sub": uid}
    signing_input = (_b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(payload).encode())).encode()
    sig = priv.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    tok = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(payload).encode()) + "." + _b64url(sig)
    if tamper:
        tok = tok[:-4] + ("AAAA" if tok.endswith("AAAA") else "BBBB")
    return tok


class TestVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        cls.priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.pub = cls.priv.public_key()
        cls.kid = "testkey"

    def _install_key(self):
        av._CERT_CACHE.clear()
        av._CERT_CACHE[self.kid] = self.pub
        av._CERT_FETCHED = time.time()

    def test_valid_token_returns_uid(self):
        av._REQUIRE_AUTH = True
        self._install_key()
        tok = _make_token(self.priv, "user_abc", kid=self.kid)
        self.assertEqual(av.verify_id_token(tok), "user_abc")

    def test_tampered_signature_rejected(self):
        av._REQUIRE_AUTH = True
        self._install_key()
        tok = _make_token(self.priv, "user_abc", kid=self.kid, tamper=True)
        self.assertRaises(ValueError, av.verify_id_token, tok)

    def test_expired_token_rejected(self):
        av._REQUIRE_AUTH = True
        self._install_key()
        tok = _make_token(self.priv, "user_abc", kid=self.kid, exp_offset=-10)
        self.assertRaises(ValueError, av.verify_id_token, tok)

    def test_bad_aud_rejected(self):
        av._REQUIRE_AUTH = True
        self._install_key()
        tok = _make_token(self.priv, "user_abc", kid=self.kid, aud="wrong-aud")
        self.assertRaises(ValueError, av.verify_id_token, tok)

    def test_resolve_rejects_when_auth_required_and_no_token(self):
        av._REQUIRE_AUTH = True
        self.assertIsNone(av.resolve_verified_uid(None, "client_uid_spoof"))

    def test_resolve_uses_verified_uid_not_client_uid(self):
        av._REQUIRE_AUTH = True
        self._install_key()
        tok = _make_token(self.priv, "real_user", kid=self.kid)
        # client claims a different uid — must be ignored
        self.assertEqual(av.resolve_verified_uid(tok, "spoofed_uid"), "real_user")

    def test_resolve_local_dev_trusts_client_uid(self):
        av._REQUIRE_AUTH = False
        self.assertEqual(av.resolve_verified_uid(None, "abc"), "abc")
        self.assertIsNone(av.resolve_verified_uid(None, None))

    def test_extract_token_from_header(self):
        headers = {"Authorization": "Bearer tok123"}
        self.assertEqual(av.extract_token(headers, {}), "tok123")

    def test_extract_token_from_body(self):
        self.assertEqual(av.extract_token({}, {"token": "bodtok"}), "bodtok")


if __name__ == "__main__":
    unittest.main()
