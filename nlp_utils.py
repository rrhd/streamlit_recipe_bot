import spacy

from constants import SPACY_MODEL

nlp = spacy.load(SPACY_MODEL)

from enum import Enum


class EntityType(Enum):
    FOOD = "FOOD"


def extract_ingredient_entities(text: str) -> list[str]:
    doc = nlp(text)
    foods = []
    for ent in doc.ents:
        if ent.label_ == EntityType.FOOD:
            foods.append(ent.text.lower().strip())
    if not foods:
        foods = [text.lower().strip()]
    return foods


def get_canonical_ingredient(text: str) -> str:
    food_ents = extract_ingredient_entities(text)
    return " ".join(food_ents) if food_ents else text.lower().strip()
