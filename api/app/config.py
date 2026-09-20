from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DDM501 Face + Voice Integrity"
    database_url: str = "sqlite:///./data/biometric.db"
    api_key: str = "demo-internal-key"
    model_backend: str = "demo"
    model_dir: str = "./models"
    face_threshold: float = 0.45
    voice_threshold: float = 0.25
    require_both_modalities: bool = True
    max_upload_mb: int = 12
    min_face_samples: int = 2
    min_voice_samples: int = 2
    store_raw_biometrics: bool = False
    biometric_bucket: str = "biometric-samples"
    mlflow_tracking_uri: str = "http://localhost:15020"
    mlflow_model_name: str = "face-voice-risk-bundle"
    mlflow_model_alias: str = "champion"
    mlflow_s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    minio_endpoint: str = "http://minio:9000"


@lru_cache
def get_settings() -> Settings:
    return Settings()

