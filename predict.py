"""Prediction wrapper for the team's YOLOv8n banana classifier."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import RLock
import math

from PIL import Image, ImageOps

MODEL_PATH = Path(__file__).resolve().parent / "models" / "banana_model.pt"
EXPECTED_NAMES = {0: "overripe", 1: "ripe", 2: "unripe"}
_LOCK = RLock()


@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.is_file():
        raise FileNotFoundError("Put banana_model.pt inside the models folder beside predict.py.")
    from ultralytics import YOLO
    model = YOLO(str(MODEL_PATH), task="classify")
    names = {int(k): str(v) for k, v in model.names.items()}
    if model.task != "classify" or names != EXPECTED_NAMES:
        raise ValueError("This is not the inspected three-class banana classifier.")
    version = "banana-yolov8n-" + sha256(MODEL_PATH.read_bytes()).hexdigest()[:12]
    return model, version


def model_info():
    with _LOCK:
        model, version = _load_model()
        return {"class_names": dict(model.names), "image_size": 224, "model_version": version}


def predict_ripeness(image):
    """Accept a Pillow image; return label, class scores, and model version.

    Ultralytics applies the checkpoint's classification transforms. Do not
    manually normalize or resize the image before calling this function.
    These scores are not calibrated accuracy or spoilage probabilities.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("Pass a Pillow Image to predict_ripeness.")
    rgb = ImageOps.exif_transpose(image).convert("RGB")
    with _LOCK:
        model, version = _load_model()
        result = model.predict(source=rgb, imgsz=224, device="cpu", verbose=False)[0]
        if result.probs is None:
            raise ValueError("The model did not return classification scores.")
        values = result.probs.data.detach().cpu().tolist()
        if len(values) != 3 or any(not math.isfinite(v) for v in values):
            raise ValueError("The model returned invalid scores.")
        scores = {str(result.names[i]): float(v) for i, v in enumerate(values)}
        label = max(scores, key=scores.get)
    return {"label": label, "scores": scores, "model_version": version}
