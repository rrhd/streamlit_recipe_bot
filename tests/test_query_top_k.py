import os
os.environ["RECIPE_DB_PATH"] = str(ROOT / "data" / "test_recipes.db")

import pytest

from query_top_k import (
    normalize_ingredient_name,
    deduplicate_candidates,
    build_candidate_urls,
    bulk_compute_coverage,
)
from nlp_utils import get_canonical_ingredient
    "keywords, expected",
    [(["steak"], True), (["tea"], False), (["mussels"], True)],
def test_keyword_basic(keywords, expected):
    assert (len(results) > 0) == expected

    "ingredients, expected_count",
    [(["flank steak"], 1), (["dragon fruit"], 0)],
def test_simple_ingredient_match(ingredients, expected_count):
    assert len(results) >= expected_count
def test_query_specific_recipe():
    ingredients = ["boneless beef chuck-eye roast", "garlic clove"]
    results = run_query(user_ingredients=ingredients, min_ing_matches=2)
    assert any("italian-beef-sandwiches" in r["url"] for r in results)


def test_build_candidate_urls():
    ingredients = ["garlic clove", "boneless beef chuckeye roast"]
    norm = [normalize_ingredient_name(i) for i in ingredients]
    cands = build_candidate_urls({}, {}, norm, min_ing_matches=2, limit=20)
    urls = [u for u, _ in cands]
    assert any("italian-beef-sandwiches" in u for u in urls)


def test_bulk_compute_coverage():
    ingredients = ["boneless beef chuck-eye roast", "garlic clove"]
    norm = [normalize_ingredient_name(i) for i in ingredients]
    cands = build_candidate_urls({}, {}, norm, min_ing_matches=2, limit=5)
    urls = [u for u, _ in cands]
    recipes = query_top_k.load_bulk_recipes(urls)
    coverage = bulk_compute_coverage(recipes, ingredients, min_pair_sim=0.9)
    for url, title, uc, rc in coverage:
        if "italian-beef-sandwiches" in url:
            assert uc == 1.0
            assert rc > 0
            break
        pytest.fail("Expected recipe not found")
def test_deduplicate_candidates():
    recipes = {
        "A": {"title": "Test Stew", "desc": "a"},
        "B": {"title": "Test Stew", "desc": "aa"},
        "C": {"title": "Other"},
    }
    candidates = [("A", 1), ("B", 2), ("C", 1)]
    deduped = deduplicate_candidates(candidates, recipes, threshold=90)
    urls = [u for u, _ in deduped]
    assert "B" in urls and "C" in urls and "A" not in urls


def test_normalize_and_canonical():
    raw = "FLANK STEAK!!"
    canon = get_canonical_ingredient(raw)
    norm = normalize_ingredient_name(canon)
    assert norm == "flank steak"
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


def test_query_flank_steak_top_results():
    expected_urls = [
        "https://www.americastestkitchen.com/recipes/4809-charcoal-grilled-stuffed-flank-steak",
        "https://www.americastestkitchen.com/recipes/9192-cast-iron-pan-seared-flank-steak-with-crispy-potatoes-and-chimichurri",
        "https://www.americastestkitchen.com/recipes/16181-ancho-rubbed-flank-steak-and-cilantro-rice-with-avocado-sauce",
    ]
    results = run_query(
        user_ingredients=["flank steak"], min_ing_matches=1, top_n_db=10
    )
    urls = [r["url"] for r in results[:3]]
    assert urls == expected_urls


def test_query_italian_beef_result():
    ingredients = ["boneless beef chuck-eye roast", "garlic clove"]
    results = run_query(user_ingredients=ingredients, min_ing_matches=2, top_n_db=5)
    assert results and results[0]["url"].endswith("chicago-italian-beef-sandwiches")


@pytest.mark.parametrize(
    "keywords",
    [["gar"], ["cress"], ["team"]],
)
def test_keyword_no_partial_matches(keywords):
    assert run_query(keywords=keywords) == []


@pytest.mark.parametrize(
    "ingredients, min_match, expect_any",
    [
        (["flank steak", "garlic clove"], 2, True),
        (["flank steak", "broccoli"], 2, False),
    ],
)
def test_multi_ingredient_query(ingredients, min_match, expect_any):
    results = run_query(user_ingredients=ingredients, min_ing_matches=min_match)
    assert (len(results) > 0) == expect_any
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
