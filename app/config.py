from pydantic_settings import BaseSettings, SettingsConfigDict


# here be defaults
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCAR_", env_file=".env", frozen=True)
    # `postgres+psycopg` -> makes sqlalchemy use the psycopg driver
    # `scar:scar` is the `username:password` for postgres
    # `@db:5432/scar` is the `host:port/database` for postgres
    database_url: str = "postgresql+psycopg://scar:scar@db:5432/scar"

    s3_bucket: str = "scar-assets"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    # endpoint the api uses for put/get, inside the docker network
    s3_internal_endpoint: str = "http://minio:9000"
    # endpoint used for the handed-out presigned URLs
    s3_public_endpoint: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    presign_ttl_seconds: int = 3600  # 1 hour

    # comma separated "key:operator_name" pairs
    admin_api_keys: str = "dev-key:dev-operator"
    # observability
    log_level: str = "INFO"

    def admin_key_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.admin_api_keys.split(","):
            pair = pair.strip()
            if not pair:
                continue
            key, _, operator = pair.partition(":")
            out[key] = operator or "unknown"
        return out
