"""Password hashing with bcrypt (max 72 bytes). Uses bcrypt directly to avoid passlib length error."""
import bcrypt

_MAX_BYTES = 72


def _to_72_bytes(plain: str) -> bytes:
    b = (plain or "").encode("utf-8")
    return b[:_MAX_BYTES] if len(b) > _MAX_BYTES else b


def hash_password(plain: str) -> str:
    p = _to_72_bytes(plain)
    return bcrypt.hashpw(p, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    p = _to_72_bytes(plain)
    h = hashed.encode("utf-8") if isinstance(hashed, str) else hashed
    return bcrypt.checkpw(p, h)
