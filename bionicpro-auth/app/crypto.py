import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TokenCipher:
    def __init__(self, secret: str):
        key_bytes = secret.encode("utf-8")
        if len(key_bytes) < 32:
            key_bytes = key_bytes.ljust(32, b"0")
        self._key = key_bytes[:32]

    def encrypt(self, value: str) -> str:
        nonce = os.urandom(12)
        aesgcm = AESGCM(self._key)
        encrypted = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + encrypted).decode("utf-8")

    def decrypt(self, value: str) -> str:
        data = base64.urlsafe_b64decode(value.encode("utf-8"))
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(self._key)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode("utf-8")