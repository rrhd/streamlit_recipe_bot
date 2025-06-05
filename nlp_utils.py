import os
from functools import lru_cache
from pathlib import Path
from enum import StrEnum

import spacy

from constants import PathName


@lru_cache(maxsize=1)
def get_nlp(model_path: str | None = None) -> spacy.language.Language:
    path = model_path or Path(PathName.SPACY_MODEL)
    return spacy.load(str(path))


class EntityType(StrEnum):
    FOOD = "FOOD"


def extract_ingredient_entities(text: str, model_path: str | None = None) -> list[str]:
    nlp = get_nlp(model_path)
    doc = nlp(text)
    foods = [ent.text.lower().strip() for ent in doc.ents if ent.label_ == EntityType.FOOD]
    if foods:
        token_count = len(text.split())
        ent_count = sum(len(f.split()) for f in foods)
        if ent_count != token_count:
            return [text.lower().strip()]
    else:
        foods = [text.lower().strip()]
    return foods


def get_canonical_ingredient(text: str, model_path: str | None = None) -> str:
    food_ents = extract_ingredient_entities(text, model_path=model_path)
    return " ".join(food_ents) if food_ents else text.lower().strip()
