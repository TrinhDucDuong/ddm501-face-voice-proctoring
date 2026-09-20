import json
import os
from dataclasses import dataclass

import mlflow
from mlflow import MlflowClient

from .config import Settings


@dataclass
class RuntimeModel:
    face_threshold: float
    voice_threshold: float
    version: str


class RegistryLoader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.current = RuntimeModel(settings.face_threshold, settings.voice_threshold, "local-default")

    def load(self) -> RuntimeModel:
        if self.settings.mlflow_s3_endpoint_url:
            os.environ["MLFLOW_S3_ENDPOINT_URL"] = self.settings.mlflow_s3_endpoint_url
        mlflow.set_tracking_uri(self.settings.mlflow_tracking_uri)
        client = MlflowClient()
        version = client.get_model_version_by_alias(self.settings.mlflow_model_name, self.settings.mlflow_model_alias)
        local_root = mlflow.artifacts.download_artifacts(
            artifact_uri=f"models:/{self.settings.mlflow_model_name}@{self.settings.mlflow_model_alias}"
        )
        candidates = list(__import__("pathlib").Path(local_root).rglob("thresholds.json"))
        if not candidates:
            raise FileNotFoundError("Model bundle không có thresholds.json")
        with open(candidates[0], encoding="utf-8") as handle:
            config = json.load(handle)
        self.current = RuntimeModel(
            face_threshold=float(config["face_threshold"]),
            voice_threshold=float(config["voice_threshold"]),
            version=str(version.version),
        )
        return self.current
