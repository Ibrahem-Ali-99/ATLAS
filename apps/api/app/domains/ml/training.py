"""Train a synthetic lead classifier and write one artifact outside the upload path."""

import uuid
from pathlib import Path
from typing import Any

import joblib
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.ml.dataset import (
    DATASET_SEED,
    DATASET_VERSION,
    FEATURES,
    baseline_predict,
    generate_leads,
    matrix,
)
from app.domains.ml.models import ModelVersion

_CACHE: dict[str, Any] = {}


def clear_model_cache() -> None:
    _CACHE.clear()


def train_lead_model() -> dict[str, Any]:
    rows = generate_leads()
    features, labels = matrix(rows)
    indexes = list(range(len(rows)))
    train_index, test_index = train_test_split(
        indexes, test_size=0.25, random_state=DATASET_SEED, stratify=labels
    )
    if set(train_index) & set(test_index):
        raise RuntimeError("train and test rows overlap")
    x_train = [features[index] for index in train_index]
    x_test = [features[index] for index in test_index]
    y_train = [labels[index] for index in train_index]
    y_test = [labels[index] for index in test_index]
    candidates = {
        "logistic_regression": _pipeline(
            LogisticRegression(max_iter=500, random_state=DATASET_SEED)
        ),
        "decision_tree": _pipeline(DecisionTreeClassifier(max_depth=4, random_state=DATASET_SEED)),
    }
    comparison: dict[str, dict[str, float]] = {
        "rule_baseline": _scores(y_test, baseline_predict(x_test))
    }
    fitted: dict[str, Pipeline] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(x_train, y_train)
        fitted[name] = pipeline
        comparison[name] = _scores(y_test, pipeline.predict(x_test))
    winner = max(
        ("logistic_regression", "decision_tree"),
        key=lambda name: (comparison[name]["f1"], name == "logistic_regression"),
    )
    calibrator, calibrated, confidence, calibrated_metrics = _calibrate(
        winner, x_train, y_train, x_test, y_test
    )
    if calibrated:
        comparison["calibrated_threshold"] = calibrated_metrics
    return {
        "dataset_version": DATASET_VERSION,
        "dataset_rows": len(rows),
        "seed": DATASET_SEED,
        "synthetic": True,
        "algorithm": winner,
        "calibrated": calibrated,
        "confidence": confidence,
        "metrics": comparison[winner],
        "comparison": comparison,
        "features": list(FEATURES),
        "excluded": ["budget_band", "converted", "status"],
        "pipeline": fitted[winner],
        "calibrator": calibrator,
        "version": f"{DATASET_VERSION}-{winner}",
    }


def _calibrate(
    winner: str,
    x_train: list[list[object]],
    y_train: list[int],
    x_test: list[list[object]],
    y_test: list[int],
) -> tuple[Any, bool, str, dict[str, float]]:
    """Fit probability calibration on the training fold only."""

    estimator = (
        LogisticRegression(max_iter=500, random_state=DATASET_SEED)
        if winner == "logistic_regression"
        else DecisionTreeClassifier(max_depth=4, random_state=DATASET_SEED)
    )
    calibrated = CalibratedClassifierCV(_pipeline(estimator), method="sigmoid", cv=3)
    try:
        calibrated.fit(x_train, y_train)
        predicted = calibrated.predict(x_test)
    except ValueError:
        return (
            None,
            False,
            "Calibration did not fit. predict_proba is not a calibrated probability.",
            {},
        )
    return (
        calibrated,
        True,
        (
            "Confidence is a sigmoid probability fitted on the training fold only. "
            "The label uses the uncalibrated classifier with the better held-out F1."
        ),
        _scores(y_test, predicted),
    )


def publish_model(db: Session) -> ModelVersion:
    trained = train_lead_model()
    pipeline = trained.pop("pipeline")
    version = str(trained["version"])
    directory = get_settings().model_storage_dir / version
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / "model.joblib"
    joblib.dump(
        {
            "pipeline": pipeline,
            "calibrator": trained.pop("calibrator"),
            "features": trained["features"],
        },
        artifact,
    )
    row = db.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if row is None:
        row = ModelVersion(id=uuid.uuid4(), version=version, artifact_path=str(artifact))
        db.add(row)
    row.algorithm = str(trained["algorithm"])
    row.dataset_version = str(trained["dataset_version"])
    row.synthetic = True
    row.metrics = {
        "served": trained["metrics"],
        "comparison": trained["comparison"],
        "confidence": trained["confidence"],
        "calibrated": trained["calibrated"],
        "features": trained["features"],
        "excluded": trained["excluded"],
        "dataset_rows": trained["dataset_rows"],
        "seed": trained["seed"],
    }
    row.artifact_path = str(artifact)
    db.commit()
    db.refresh(row)
    clear_model_cache()
    return row


def _pipeline(estimator: LogisticRegression | DecisionTreeClassifier) -> Pipeline:
    prepare = ColumnTransformer(
        transformers=[
            (
                "category",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                [0, 5],
            ),
            ("number", "passthrough", [1, 2, 3, 4]),
        ]
    )
    return Pipeline([("prepare", prepare), ("model", estimator)])


def _scores(y_true: list[int], predicted: Any) -> dict[str, float]:
    return {
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 6),
    }


def load_pipeline(version: ModelVersion) -> Any:
    cached = _CACHE.get("version")
    if cached == str(version.id):
        return _CACHE["pipeline"]
    path = _artifact_path(version)
    if not path.is_file():
        raise FileNotFoundError(path)
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or "pipeline" not in bundle:
        raise ValueError("model artifact is missing a pipeline")
    _CACHE["version"] = str(version.id)
    _CACHE["pipeline"] = bundle
    return bundle


def _artifact_path(version: ModelVersion) -> Path:
    root = get_settings().model_storage_dir.resolve()
    path = Path(version.artifact_path).resolve()
    if path.suffix != ".joblib" or (path != root and root not in path.parents):
        raise ValueError("model artifact is outside the model directory")
    return path
