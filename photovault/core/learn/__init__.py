"""Stage A orchestration: catalogs -> Taste Profile."""

from photovault.core.learn.classifier import (
    KeepRejectModel,
    predict_proba,
    train_classifier,
)
from photovault.core.learn.pipeline import LearnReport, learn_from_folder
from photovault.core.learn.taste import compute_taste_vector, similarity
from photovault.core.learn.vectorstore import (
    InMemoryVectorStore,
    VectorStore,
    get_vectorstore,
)

__all__ = [
    "InMemoryVectorStore",
    "KeepRejectModel",
    "LearnReport",
    "VectorStore",
    "compute_taste_vector",
    "get_vectorstore",
    "learn_from_folder",
    "predict_proba",
    "similarity",
    "train_classifier",
]
