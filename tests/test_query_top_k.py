
import pytest
import query_top_k
from constants import PROJECT_DIR

query_top_k.DATABASE = PROJECT_DIR / 'data/test_recipes.db'

def run_query(keywords=None, user_ingredients=None, min_ing_matches=None, top_n_db=10):
    if keywords is None:
        keywords = []
    if user_ingredients is None:
        user_ingredients = []
    if min_ing_matches is None:
        min_ing_matches = 1 if user_ingredients else 0
    return query_top_k.query_top_k(
        user_ingredients=user_ingredients,
        tag_filters={},
        excluded_tags={},
        keywords_to_include=keywords,
        min_ing_matches=min_ing_matches,
        top_n_db=top_n_db,
    )



@pytest.mark.parametrize(
    "keywords, expected_min",
    [
        (["steak"], 5),
        (["tea"], 0),
        (["steam"], 2),
    ],
)
def test_keyword_matching(keywords, expected_min):
    results = run_query(keywords=keywords)
    if expected_min == 0:
        assert len(results) == 0
    else:
        assert len(results) >= expected_min

@pytest.mark.parametrize(
    "ingredients, expected_min",
    [
        (["flank steak"], 1),
        (["brown sugar"], 5),
        (["brown"], 0),
        (["tea"], 0),
    ],
)
def test_exact_ingredient_matching(ingredients, expected_min):
    results = run_query(user_ingredients=ingredients)
    if expected_min == 0:
        assert len(results) == 0
    else:
        assert len(results) >= expected_min


@pytest.mark.parametrize(
    "keywords, expected_min",
    [
        (["mussels"], 1),
        (["Pho"], 1),
        (["crab", "shrimp"], 1),
        (["Chicago", "beef"], 2),
        (["tea", "sugar"], 0),
    ],
)
def test_keyword_combinations(keywords, expected_min):
    results = run_query(keywords=keywords)
    if expected_min == 0:
        assert len(results) == 0
    else:
        assert len(results) >= expected_min


@pytest.mark.parametrize(
    "ingredients, min_matches, expected_min",
    [
        (["unsalted butter", "garlic clove"], 2, 19),
        (["unsalted butter", "peanut butter"], 2, 1),
        (["unsalted butter", "sugar"], 2, 24),
    ],
)
def test_multi_ingredient_matching(ingredients, min_matches, expected_min):
    results = run_query(user_ingredients=ingredients, min_ing_matches=min_matches, top_n_db=3000)
    assert len(results) >= expected_min
