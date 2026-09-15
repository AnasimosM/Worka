from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Insight MVP"
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite:///./insight_mvp.db"
    upload_dir: str = "./uploads"
    legal_ruleset: str = "demo_us_general.json"
    payments_mode: str = "demo"
    external_escrow_provider_name: str = "Approved external provider"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

settings = Settings()
