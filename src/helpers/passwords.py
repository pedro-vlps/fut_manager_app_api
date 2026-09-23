"""Hash e verificação de senhas sem persistir texto puro."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import scrypt
from hmac import compare_digest
from secrets import token_bytes

_ALGORITHM = "scrypt"
_N = 2**14
_R = 8
_P = 1
_KEY_LENGTH = 64


def hash_password(password: str) -> str:
    """Gera um hash scrypt com salt aleatório para armazenar no banco."""
    if len(password) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")

    salt = token_bytes(16)
    password_hash = scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_KEY_LENGTH
    )
    return "$".join(
        (
            _ALGORITHM,
            str(_N),
            str(_R),
            str(_P),
            urlsafe_b64encode(salt).decode("ascii"),
            urlsafe_b64encode(password_hash).decode("ascii"),
        )
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Compara uma senha com o hash persistido, em tempo constante."""
    try:
        algorithm, n, r, p, salt, expected_hash = stored_hash.split("$")
        if algorithm != _ALGORITHM:
            return False
        computed_hash = scrypt(
            password.encode("utf-8"),
            salt=urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=_KEY_LENGTH,
        )
        return compare_digest(computed_hash, urlsafe_b64decode(expected_hash))
    except (TypeError, ValueError):
        return False
