from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GestinemAppFull API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    debug: bool = True

    postgres_server: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "gestinem"
    postgres_password: str = "gestinem"
    postgres_db: str = "gestinemappfull"

    secret_key: str = "change-this-in-production"
    access_token_expire_minutes: int = 60
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="GESTINEMAPPFULL_",
    )

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_server}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
