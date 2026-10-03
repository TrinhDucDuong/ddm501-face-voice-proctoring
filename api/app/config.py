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
    enable_simulation: bool = False
    store_raw_biometrics: bool = False
    biometric_bucket: str = "biometric-samples"
    mlflow_tracking_uri: str = "http://localhost:15020"
    mlflow_model_name: str = "face-voice-risk-bundle"
    mlflow_model_alias: str = "champion"
    mlflow_s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    minio_endpoint: str = "http://minio:9000"
    public_api_url: str = "http://localhost:18100"
    webhook_master_key: str = ""
    session_signing_key: str = ""
    webhook_allowed_hosts: str = "legacy-demo,localhost,127.0.0.1"
    allow_insecure_webhooks: bool = True
    webhook_max_attempts: int = 5
    enable_demo_registration: bool = True
    face_spoof_threshold: float = 0.5
    audio_spoof_threshold: float = 0.5
    speaker_change_threshold: float = 0.35
    retain_monitoring_embeddings: bool = False
    monitoring_embedding_retention_days: int = 30
    lifecycle_config_path: str = './pipeline/lifecycle_config.json'
    continuous_training_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
