import hashlib
import secrets


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("A senha deve conter entre 12 e 128 caracteres.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or len(password) > 128:
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024
        )
        return secrets.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
