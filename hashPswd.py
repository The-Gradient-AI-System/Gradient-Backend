"""Password hashing using passlib (bcrypt). Bcrypt accepts max 72 bytes."""
from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_MAX_BCRYPT_BYTES = 72


def _truncate_to_72_bytes(s: str) -> str:
    b = s.encode("utf-8")
    if len(b) <= _MAX_BCRYPT_BYTES:
        return s
    return b[:_MAX_BCRYPT_BYTES].decode("utf-8", errors="ignore")


def hash_password(plain: str) -> str:
    return _ctx.hash(_truncate_to_72_bytes(plain))


def verify_password(plain: str, hashed: str) -> bool:
    return _ctx.verify(_truncate_to_72_bytes(plain), hashed)
