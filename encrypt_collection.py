"""Encrypts collection.json with a passphrase for client-side decryption via Web Crypto API."""

import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt(data: bytes, passphrase: str) -> dict:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 100_000)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, data, None)
    return {
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "data": base64.b64encode(ciphertext).decode(),
    }


def main():
    passphrase = os.environ.get("PASSPHRASE")
    if not passphrase:
        print("Set the PASSPHRASE environment variable")
        sys.exit(1)

    with open("collection.json", "rb") as f:
        data = f.read()

    encrypted = encrypt(data, passphrase)

    with open("site/collection.enc.json", "w") as f:
        json.dump(encrypted, f)

    print(f"Encrypted {len(data)} bytes -> site/collection.enc.json")


if __name__ == "__main__":
    main()
