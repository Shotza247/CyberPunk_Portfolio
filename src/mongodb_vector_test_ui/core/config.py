import os
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass(frozen=True)
class Settings:
    env_file: str = ""
    app_env: str = "local"
    mongodb_uri: str = ""
    mongodb_db: str = "RAG_with_MongoDB"
    mongodb_collection: str = "profile_chunks"
    vector_index_name: str = "profile_vector_index"
    vector_field: str = "embedding"
    vector_dimensions: int = 1024
    vector_num_candidates: int = 150
    embedding_provider: str = "voyage"
    voyage_base_url: str = "https://ai.mongodb.com/v1"
    voyage_api_key: str = ""
    voyage_model: str = "voyage-context-4"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    frontend_origins: tuple[str, ...] = ()
    admin_username: str = ""
    admin_email: str = ""
    admin_password_hash: str = ""
    admin_auth_secret: str = ""
    admin_session_ttl_seconds: int = 3600
    badge_collection: str = "portfolio_badges"
    metrics_collection: str = "rag_operation_metrics"


INVALID_DATABASE_CHARS = frozenset('/\\."$\x00')


@lru_cache
def get_settings() -> Settings:
    env_file = Path(os.getenv("ENV_FILE", Path.cwd() / ".env")).expanduser().resolve()
    if load_dotenv is not None:
        load_dotenv(env_file, override=True)
    return Settings(
        env_file=str(env_file),
        app_env=_str("APP_ENV", Settings.app_env),
        mongodb_uri=_str("MONGODB_URI", Settings.mongodb_uri),
        mongodb_db=_str("MONGODB_DB", Settings.mongodb_db),
        mongodb_collection=_str("MONGODB_COLLECTION", Settings.mongodb_collection),
        vector_index_name=_str("VECTOR_INDEX_NAME", Settings.vector_index_name),
        vector_field=_str("VECTOR_FIELD", Settings.vector_field),
        vector_dimensions=_int("VECTOR_DIMENSIONS", Settings.vector_dimensions),
        vector_num_candidates=_int("VECTOR_NUM_CANDIDATES", Settings.vector_num_candidates),
        embedding_provider=_str("EMBEDDING_PROVIDER", Settings.embedding_provider),
        voyage_base_url=_str("VOYAGE_BASE_URL", Settings.voyage_base_url).rstrip("/"),
        voyage_api_key=_str("VOYAGE_API_KEY", Settings.voyage_api_key),
        voyage_model=_str("VOYAGE_MODEL", Settings.voyage_model),
        openai_api_key=_str("OPENAI_API_KEY", Settings.openai_api_key),
        openai_embedding_model=_str("OPENAI_EMBEDDING_MODEL", Settings.openai_embedding_model),
        frontend_origins=tuple(
            origin.strip().rstrip("/")
            for origin in _str("FRONTEND_ORIGINS", "").split(",")
            if origin.strip()
        ),
        admin_username=_str("ADMIN_USERNAME", Settings.admin_username),
        admin_email=_str("ADMIN_EMAIL", Settings.admin_email).lower(),
        admin_password_hash=_str("ADMIN_PASSWORD_HASH", Settings.admin_password_hash),
        admin_auth_secret=_str("ADMIN_AUTH_SECRET", Settings.admin_auth_secret),
        admin_session_ttl_seconds=_int(
            "ADMIN_SESSION_TTL_SECONDS", Settings.admin_session_ttl_seconds
        ),
        badge_collection=_str("BADGE_COLLECTION", Settings.badge_collection),
        metrics_collection=_str("METRICS_COLLECTION", Settings.metrics_collection),
    )


def _str(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def safe_diagnostics(settings: Settings) -> dict:
    host = mongodb_host(settings.mongodb_uri)
    return {
        "env_file": settings.env_file,
        "mongodb_uri_set": bool(settings.mongodb_uri),
        "mongodb_uri_length": len(settings.mongodb_uri),
        "mongodb_uri_starts_valid_scheme": settings.mongodb_uri.startswith(
            ("mongodb+srv://", "mongodb://")
        ),
        "mongodb_uri_at_count": settings.mongodb_uri.count("@"),
        "mongodb_host": host,
        "mongodb_host_looks_placeholder": _looks_placeholder(host),
        "mongodb_db": settings.mongodb_db,
        "mongodb_collection": settings.mongodb_collection,
        "vector_index_name": settings.vector_index_name,
        "vector_field": settings.vector_field,
        "vector_dimensions": settings.vector_dimensions,
        "embedding_provider": settings.embedding_provider,
        "voyage_base_url": settings.voyage_base_url if settings.embedding_provider == "voyage" else None,
        "voyage_api_key_set": bool(settings.voyage_api_key),
        "voyage_model": settings.voyage_model,
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_embedding_model": settings.openai_embedding_model,
        "frontend_origin_count": len(settings.frontend_origins),
        "admin_auth_configured": bool(
            settings.admin_username
            and settings.admin_email
            and settings.admin_password_hash
            and settings.admin_auth_secret
        ),
        "badge_collection": settings.badge_collection,
        "metrics_collection": settings.metrics_collection,
    }


def validate_settings(settings: Settings) -> list[str]:
    issues: list[str] = []
    host = mongodb_host(settings.mongodb_uri)
    if not settings.mongodb_uri:
        issues.append("MONGODB_URI is missing.")
    elif not host:
        issues.append(
            "MONGODB_URI is set but malformed. It must start with mongodb+srv:// or "
            "mongodb:// and include username:password@cluster-host. If the password has "
            "special characters such as #, @, /, ?, :, or %, URL-encode the password."
        )
    elif _looks_placeholder(host):
        issues.append(
            "MONGODB_URI still looks like a placeholder. Replace CLUSTER.mongodb.net with "
            "the exact Atlas hostname from Connect, for example cluster0.xxxxx.mongodb.net."
        )

    provider = settings.embedding_provider.lower()
    if provider == "voyage" and not settings.voyage_api_key:
        issues.append("VOYAGE_API_KEY is missing for EMBEDDING_PROVIDER=voyage.")
    if provider == "openai" and not settings.openai_api_key:
        issues.append("OPENAI_API_KEY is missing for EMBEDDING_PROVIDER=openai.")
    if settings.admin_session_ttl_seconds < 300 or settings.admin_session_ttl_seconds > 86400:
        issues.append("ADMIN_SESSION_TTL_SECONDS must be between 300 and 86400.")
    if not settings.badge_collection or "\x00" in settings.badge_collection:
        issues.append("BADGE_COLLECTION must be a non-empty MongoDB collection name.")
    if settings.badge_collection == settings.mongodb_collection:
        issues.append("BADGE_COLLECTION must be separate from MONGODB_COLLECTION.")
    if not settings.metrics_collection or "\x00" in settings.metrics_collection:
        issues.append("METRICS_COLLECTION must be a non-empty MongoDB collection name.")
    if settings.metrics_collection.startswith("system."):
        issues.append("METRICS_COLLECTION cannot use the MongoDB system. namespace.")
    if settings.metrics_collection in {settings.mongodb_collection, settings.badge_collection}:
        issues.append("METRICS_COLLECTION must be separate from the vector and badge collections.")
    if not settings.frontend_origins:
        issues.append("FRONTEND_ORIGINS is empty; browser API requests will be blocked by CORS.")
    elif any(not _is_safe_frontend_origin(origin) for origin in settings.frontend_origins):
        issues.append("FRONTEND_ORIGINS must contain exact HTTPS origins (HTTP is allowed for localhost only).")
    if settings.admin_username or settings.admin_email or settings.admin_password_hash:
        if not settings.admin_username:
            issues.append("ADMIN_USERNAME is required when configuring admin authentication.")
        if not settings.admin_email:
            issues.append("ADMIN_EMAIL is required when configuring admin authentication.")
        if not settings.admin_password_hash:
            issues.append("ADMIN_PASSWORD_HASH is required when configuring admin authentication.")
        if len(settings.admin_auth_secret) < 32:
            issues.append("ADMIN_AUTH_SECRET must contain at least 32 characters.")
        if not 300 <= settings.admin_session_ttl_seconds <= 86400:
            issues.append("ADMIN_SESSION_TTL_SECONDS must be between 300 and 86400.")
    return issues


def validated_frontend_origins(settings: Settings) -> list[str]:
    invalid = [origin for origin in settings.frontend_origins if not _is_safe_frontend_origin(origin)]
    if invalid:
        raise ValueError(
            "FRONTEND_ORIGINS must use exact HTTPS origins, or HTTP localhost origins for development."
        )
    return list(settings.frontend_origins)


def with_mongodb_target(settings: Settings, database: str = "", collection: str = "") -> Settings:
    database = _clean_database_name(database or settings.mongodb_db)
    collection = _clean_collection_name(collection or settings.mongodb_collection)
    return replace(settings, mongodb_db=database, mongodb_collection=collection)


def mongodb_host(uri: str) -> str:
    if not uri:
        return ""
    parsed = urlparse(uri)
    return parsed.hostname or ""


def _is_safe_frontend_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or origin == "*"
    ):
        return False
    return parsed.scheme == "https" or parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def _looks_placeholder(value: str) -> bool:
    lowered = value.lower()
    return "cluster.mongodb.net" in lowered or "user" in lowered or "password" in lowered


def _clean_database_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("MongoDB database name is required.")
    if len(cleaned.encode()) > 63:
        raise ValueError("MongoDB database name must be 63 bytes or fewer.")
    if any(char in INVALID_DATABASE_CHARS for char in cleaned):
        raise ValueError('MongoDB database name cannot contain /, \\, ., ", $, or null characters.')
    return cleaned


def _clean_collection_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("MongoDB collection name is required.")
    if "\x00" in cleaned:
        raise ValueError("MongoDB collection name cannot contain null characters.")
    if cleaned.startswith("system."):
        raise ValueError("System collections are not valid portfolio operations targets.")
    return cleaned
