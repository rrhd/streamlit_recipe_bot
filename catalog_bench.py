"""catalog_bench.py
Clean, extensible benchmark for taxonomy-classification pipelines.

Python 3.12 – no external config files; override any field via
CLI (--field value) or env var `CATBENCH_<FIELD>`.

Linted with ruff / black-S, mypy-clean.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import os
import random
from collections import Counter
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Callable

import numpy as np
from faker import Faker
from pydantic import BaseModel, Field, model_validator
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier


def init_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("bench")


# ────────────────────────────────────────────────────────────────
# 1. Config & taxonomy templates
# ----------------------------------------------------------------


class Tier(IntEnum):
    """Benchmark complexity tiers."""

    EASY = 0
    NOISY = 1
    IMBALANCED = 2


class ModelID(StrEnum):
    """Available model names."""

    RANDOM = "random"
    MAJORITY = "majority"
    TFIDF_LR = "tfidf_lr"
    TFIDF_KNN = "tfidf_knn"
    BERT_MINI = "bert_mini"


class KNNParam(IntEnum):
    """KNN hyper-parameters."""

    K = 5


class Settings(BaseModel):
    """Run-time configuration; override via CLI or env."""

    seed: int = Field(42, description="Global RNG seed")
    samples_per_class: int = Field(1_200, gt=0)
    bootstrap_samples: int = Field(500, gt=50)
    max_vocab: int = Field(60_000, gt=10_000)
    enable_bert: bool = Field(False, description="Fine-tune BERT-mini")
    tiers: list[Tier] = Field([Tier.EASY, Tier.NOISY, Tier.IMBALANCED])

    @model_validator(mode="after")
    def _set_seed(self) -> "Settings":
        random.seed(self.seed)
        np.random.seed(self.seed)
        return self


CFG = Settings.model_validate({k.lower(): v for k, v in os.environ.items() if k.startswith("CATBENCH_")})

TEMPLATES: dict[str, dict[str, list[str]]] = {
    "electronics.smartphone": {
        "kw": ["smartphone", "mobile phone", "cell phone"],
        "adj": ["5G", "dual-SIM", "OLED", "128 GB"],
    },
    "electronics.laptop": {
        "kw": ["laptop", "notebook", "ultrabook"],
        "adj": ["15-inch", "touchscreen", "Ryzen", "16 GB RAM"],
    },
    "apparel.tshirt": {
        "kw": ["t-shirt", "tee", "shirt"],
        "adj": ["cotton", "graphic", "oversized", "crew-neck"],
    },
    "apparel.jeans": {
        "kw": ["jeans", "denim pants", "slim jeans"],
        "adj": ["slim-fit", "stretch", "mid-rise", "dark wash"],
    },
    "home.kitchen": {
        "kw": ["blender", "toaster", "food processor"],
        "adj": ["stainless", "digital", "1200 W", "compact"],
    },
    "home.furniture": {
        "kw": ["sofa", "coffee table", "bookshelf"],
        "adj": ["mid-century", "oak", "modular", "low-profile"],
    },
}
LABELS = list(TEMPLATES)

FAKER = Faker()


def _rand_text(label: str, hard: bool) -> str:
    tpl = TEMPLATES[label]
    title = f"{FAKER.company()} {random.choice(tpl['adj'])} {random.choice(tpl['kw'])}"
    if hard:
        title = f"{FAKER.word()} {title} {FAKER.word()}"
    desc = FAKER.sentence(nb_words=10)
    if hard:
        desc += f" {FAKER.bs()}"
    return f"{title}. {desc}"


TIER_CFG: dict[Tier, dict[str, Any]] = {
    Tier.EASY: {"noise": 0.0, "hard": False, "imbalance": [1] * len(LABELS)},
    Tier.NOISY: {"noise": 0.03, "hard": True, "imbalance": [1] * len(LABELS)},
    Tier.IMBALANCED: {"noise": 0.05, "hard": True, "imbalance": [5, 5, 1, 1, 1, 1]},
}


def build_dataset(tier: Tier) -> tuple[list[str], list[str]]:
    cfg = TIER_CFG[tier]
    x, y = [], []
    for idx, label in enumerate(LABELS):
        reps = CFG.samples_per_class * cfg["imbalance"][idx]
        for _ in range(reps):
            x.append(_rand_text(label, cfg["hard"]))
            y.append(label)
    # label noise
    n_noise = int(len(y) * cfg["noise"])
    for i in np.random.choice(len(y), n_noise, False):
        y[i] = random.choice(LABELS)
    return x, y


# ────────────────────────────────────────────────────────────────
# 3. Model registry
# ----------------------------------------------------------------


class BaseModelWrapper:
    name: ModelID

    def fit(self, x: list[str], y: list[str]) -> None: ...

    def predict(self, x: list[str]) -> list[str]: ...


_REGISTRY: dict[ModelID, Callable[[], BaseModelWrapper]] = {}


def _register(mid: ModelID) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _REGISTRY[mid] = cls  # type: ignore
        cls.name = mid
        return cls

    return decorator


@_register(ModelID.RANDOM)
class RandomModel(BaseModelWrapper):
    def fit(self, x: list[str], y: list[str]) -> None: ...

    def predict(self, x: list[str]) -> list[str]:
        return list(np.random.choice(LABELS, len(x)))


@_register(ModelID.MAJORITY)
class MajorityModel(BaseModelWrapper):
    _major: str

    def fit(self, x: list[str], y: list[str]) -> None:
        self._major = Counter(y).most_common(1)[0][0]

    def predict(self, x: list[str]) -> list[str]:
        return [self._major] * len(x)


@_register(ModelID.TFIDF_LR)
class TfidfLogReg(BaseModelWrapper):
    def __init__(self) -> None:
        self.vec = TfidfVectorizer(max_features=CFG.max_vocab, ngram_range=(1, 2))
        self.clf = LogisticRegression(max_iter=1_000, multi_class="multinomial")

    def fit(self, x: list[str], y: list[str]) -> None:
        self.clf.fit(self.vec.fit_transform(x), y)

    def predict(self, x: list[str]) -> list[str]:
        return self.clf.predict(self.vec.transform(x)).tolist()  # type: ignore


@_register(ModelID.TFIDF_KNN)
class TfidfKNN(BaseModelWrapper):
    def __init__(self, k: int = KNNParam.K) -> None:
        self.vec = TfidfVectorizer(max_features=CFG.max_vocab, ngram_range=(1, 2))
        self.knn = KNeighborsClassifier(int(k), metric="cosine")

    def fit(self, x: list[str], y: list[str]) -> None:
        self.knn.fit(self.vec.fit_transform(x), y)

    def predict(self, x: list[str]) -> list[str]:
        return self.knn.predict(self.vec.transform(x)).tolist()


if CFG.enable_bert:

    @_register(ModelID.BERT_MINI)
    class BertMini(BaseModelWrapper):  # pragma: no cover  (heavy)
        def __init__(self) -> None:
            from datasets import Dataset
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                Trainer,
                TrainingArguments,
            )

            self._id_map = {lbl: i for i, lbl in enumerate(LABELS)}
            self._tok = AutoTokenizer.from_pretrained("microsoft/bert-mini")
            self._model = AutoModelForSequenceClassification.from_pretrained(
                "microsoft/bert-mini", num_labels=len(LABELS)
            )
            self._Trainer = Trainer
            self._TArgs = TrainingArguments
            self._Dataset = Dataset

        def _encode(self, batch: dict[str, list[str]]) -> dict[str, Any]:
            return self._tok(
                batch["text"], truncation=True, padding="max_length", max_length=128
            )

        def fit(self, x: list[str], y: list[str]) -> None:
            ds = self._Dataset.from_dict(
                {"text": x, "label": [self._id_map[l] for l in y]}
            ).train_test_split(test_size=0.1, seed=CFG.seed)
            ds = ds.map(self._encode, batched=True).remove_columns("text")
            args = self._TArgs(
                output_dir=Path("bert_runs").as_posix(),
                per_device_train_batch_size=32,
                learning_rate=2e-5,
                num_train_epochs=2,
                fp16=True,
                save_strategy="no",
                report_to="none",
                seed=CFG.seed,
            )
            self._Trainer(
                model=self._model, args=args, train_dataset=ds["train"]
            ).train()

        def predict(self, x: list[str]) -> list[str]:
            t = self._tok(
                x, truncation=True, padding="max_length", max_length=128, return_tensors="pt"
            )
            logits = self._model(**t).logits
            return [LABELS[i] for i in logits.argmax(-1).tolist()]


# ────────────────────────────────────────────────────────────────
# 4. Evaluation helpers
# ----------------------------------------------------------------


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    return f1_score(y_true, y_pred, average="macro")


def bootstrap_ci(
    y: list[str], a: list[str], b: list[str], samples: int = CFG.bootstrap_samples
) -> tuple[float, float]:
    idx = np.arange(len(y))
    diffs = []
    for _ in range(samples):
        s = np.random.choice(idx, len(idx), True)
        diffs.append(macro_f1(np.take(y, s), np.take(a, s)) - macro_f1(np.take(y, s), np.take(b, s)))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


# ────────────────────────────────────────────────────────────────
# 5. Main benchmark loop
# ----------------------------------------------------------------


def run_tier(tier: Tier) -> None:
    x, y = build_dataset(tier)
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.2, stratify=y, random_state=CFG.seed)

    results: dict[str, dict[str, Any]] = {}
    for mid in _REGISTRY:
        mdl = _REGISTRY[mid]()
        mdl.fit(x_tr, y_tr)
        yp = mdl.predict(x_te)
        f1 = macro_f1(y_te, yp)
        acc = accuracy_score(y_te, yp)
        results[mid] = {"f1": f1, "acc": acc, "pred": yp}
        LOGGER.info("T%s %s F1=%.3f Acc=%.3f", tier.value, mid, f1, acc)

    rand_exp = 1 / len(LABELS)
    assert abs(results[ModelID.RANDOM]["acc"] - rand_exp) < 0.05, "Random acc deviates from theory"

    maj_share = Counter(y_tr).most_common(1)[0][1] / len(y_tr)
    assert abs(results[ModelID.MAJORITY]["acc"] - maj_share) < 0.05, "Majority acc off baseline"

    assert (
        results[ModelID.TFIDF_LR]["f1"] > results[ModelID.RANDOM]["f1"] + 0.2
    ), "LogReg barely beats random"

    if tier is Tier.IMBALANCED:
        assert results[ModelID.TFIDF_LR]["f1"] > 0.7, "Imbalanced tier F1 too low"

    for a, b in itertools.combinations(_REGISTRY, 2):
        lo, hi = bootstrap_ci(y_te, results[a]["pred"], results[b]["pred"])
        LOGGER.info("   ΔF1 %s–%s: [%+.3f,%+.3f]", a, b, lo, hi)


def _parse_cli() -> Settings:
    """Allow CLI overrides without external files."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples_per_class", type=int)
    parser.add_argument("--enable_bert", action="store_true")
    args = vars(parser.parse_args())
    clean = {k: v for k, v in args.items() if v is not None}
    return CFG.model_copy(update=clean)


if __name__ == "__main__":
    CFG = _parse_cli()
    LOGGER = init_logging()
    LOGGER.info("Config", extra=CFG.model_dump(exclude_none=True))
    for t in CFG.tiers:
        run_tier(t)
