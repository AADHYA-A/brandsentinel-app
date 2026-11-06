from __future__ import annotations
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator
from .config import settings


def _fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        f = settings.data_path / ".enc_key"
        if f.exists():
            key = f.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            f.write_text(key)
            try:
                f.chmod(0o600)
            except OSError:
                pass
    return Fernet(key.encode() if isinstance(key, str) else key)


FERNET = _fernet()


class EncryptedText(TypeDecorator):
    """Draft text is encrypted at rest (Fernet / AES-128-CBC + HMAC)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else FERNET.encrypt(value.encode("utf-8")).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return FERNET.decrypt(value.encode()).decode("utf-8")
        except InvalidToken:
            return "[unreadable: wrong encryption key]"


class Base(DeclarativeBase):
    pass


_url = settings.database_url
_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(_url, connect_args=_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
