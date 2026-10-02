import json
import math
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
            artifact_uri=f"models:/{self.settings.mlflow_model_name}/{version.version}"
        )
        candidates = list(__import__("pathlib").Path(local_root).rglob("thresholds.json"))
        if not candidates:
            raise FileNotFoundError("Model bundle không có thresholds.json")
        with open(candidates[0], encoding="utf-8") as handle:
            config = json.load(handle)
        thresholds = [float(config[key]) for key in ("face_threshold", "voice_threshold")]
        if any(not math.isfinite(value) or not -1 <= value <= 1 for value in thresholds):
            raise ValueError("Invalid registered biometric thresholds")
        self.current = RuntimeModel(
            face_threshold=thresholds[0],
            voice_threshold=thresholds[1],
            version=str(version.version),
        )
        return self.current
