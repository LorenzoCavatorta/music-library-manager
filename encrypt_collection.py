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

    with open("collection.json") as f:
        collection = json.load(f)

    payload = {"collection": collection}

    if os.path.exists("config.json"):
        with open("config.json") as f:
            payload["config"] = json.load(f)
        print("Bundling config.json into encrypted payload")

    gh_issues_token = os.environ.get("GH_ISSUES_TOKEN")
    if gh_issues_token:
        payload["gh_issues_token"] = gh_issues_token
        print("Bundling GH_ISSUES_TOKEN into encrypted payload")

    data = json.dumps(payload, ensure_ascii=False).encode()
    encrypted = encrypt(data, passphrase)

    with open("site/collection.enc.json", "w") as f:
        json.dump(encrypted, f)

    print(f"Encrypted {len(data)} bytes -> site/collection.enc.json")


if __name__ == "__main__":
    main()
