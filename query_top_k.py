import json
import logging
import re
import sqlite3

import numpy as np
import pandas as pd
import spacy
from rapidfuzz import fuzz
from rapidfuzz.process import cdist
from scipy.optimize import linear_sum_assignment

from constants import SPACY_MODEL
from nlp_utils import get_canonical_ingredient

DATABASE = "data/recipe_links.db"
CONCURRENCY_LIMIT = 5


nlp = spacy.load(SPACY_MODEL)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d: %(message)s",
)


def get_db_connection():
    return sqlite3.connect(DATABASE)


def normalize_ingredient_name(text: str) -> str:
    """
    Lowercase, remove punctuation, collapse multiple spaces.
    Matches how we stored 'normalized_ingredient' in DB.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def deduplicate_candidates(
    candidates: list[tuple[str, int]],
    recipes_dict: dict[str, dict],
    threshold: float = 95,
) -> list[tuple[str, int]]:
    """
    Deduplicate candidate recipes in batch by computing a pairwise similarity matrix on their titles.
    Candidates is a list of tuples (url, matched_count). For each candidate, the recipe title is obtained
    from recipes_dict (here, the URL is used as the title). If the fuzzy similarity between two candidate titles
    (using fuzz.token_set_ratio) is at least `threshold`, keep the candidate whose JSON dump (of its recipe dict)
    is longer.
    """
    n = len(candidates)
    if n == 0:
        return []

    candidate_urls = np.array([url for url, _ in candidates])

    sim_matrix = cdist(candidate_urls, candidate_urls, scorer=fuzz.token_set_ratio)

    lengths = np.array([len(json.dumps(recipes_dict[url])) for url in candidate_urls])

    i_indices, j_indices = np.triu_indices(n, k=1)

    mask = sim_matrix[i_indices, j_indices] >= threshold
    i_sel = i_indices[mask]
    j_sel = j_indices[mask]

    drop_indices = np.where(lengths[i_sel] >= lengths[j_sel], j_sel, i_sel)

    keep = np.ones(n, dtype=bool)

    keep[np.unique(drop_indices)] = False

    deduped_candidates = [candidates[i] for i in range(n) if keep[i]]
    return deduped_candidates


def build_candidate_urls(
    tag_filters: dict[str, list[str]],
    excluded_tags: dict[str, list[str]],
    user_ingredients: list[str],
    min_ing_matches: int,
    forbidden_ingredients: list[str] = None,
    must_use: list[str] = None,
    tag_filter_mode: str = "AND",
    max_steps: int = 0,
    keywords_to_include: list[str] = None,
    keywords_to_exclude: list[str] = None,
    sources: list[str] = None,
    limit: int = 3000,
) -> list[tuple[str, int]]:
    """
    Returns a list of (url, matched_count) for recipes that:
      1) match the user's chosen tags (OR logic among each category),
      2) do *not* contain any tags from excluded_tags,
      3) contain at least 'min_ing_matches' distinct user ingredients,
      4) do not contain any forbidden ingredients,
      5) include each must_use ingredient,
      6) have step_count <= max_steps (if max_steps > 0),
      7) match additional keyword inclusion/exclusion criteria,
      8) sorted by matched_count descending (and limited to 'limit' rows).
    """

    if not keywords_to_include:
        keywords_to_include = []
    if not keywords_to_exclude:
        keywords_to_exclude = []
    if not forbidden_ingredients:
        forbidden_ingredients = []
    if not must_use:
        must_use = []

    needed_categories = []
    tag_or_clauses = []
    tag_params = []
    for cat, chosen_titles in tag_filters.items():
        if chosen_titles:
            needed_categories.append(cat)
            placeholders = ",".join(["?"] * len(chosen_titles))
            tag_or_clauses.append(f"(t.category = ? AND t.title IN ({placeholders}))")
            tag_params.append(cat)
            tag_params.extend(chosen_titles)

    if tag_or_clauses:
        tag_filter_clause = " OR ".join(tag_or_clauses)
        needed_tags_count = len(needed_categories)
    else:
        tag_filter_clause = None
        needed_tags_count = 0

    sql = """
    SELECT
        s.url,
        COUNT(DISTINCT i.normalized_ingredient) AS matched_count,
        COUNT(DISTINCT t.category) AS matched_categories,
        COALESCE(st.step_count, 0) AS step_count
    FROM recipe_schema s
    JOIN recipe_tags t
      ON s.url = t.url
    JOIN recipe_ingredients i
      ON s.url = i.url
    LEFT JOIN (
      SELECT url, COUNT(*) AS step_count
      FROM recipe_instructions
      GROUP BY url
    ) st ON s.url = st.url
    """

    where_parts = []
    final_params = []

    if sources:
        placeholders = ",".join(["?"] * len(sources))
        where_parts.append(f"s.source_domain IN ({placeholders})")
        final_params.extend(sources)

    if tag_filter_clause:
        where_parts.append(f"({tag_filter_clause})")
        final_params.extend(tag_params)

    exclude_clauses = []
    exclude_params = []
    for cat, ex_titles in excluded_tags.items():
        if ex_titles:
            placeholders = ",".join(["?"] * len(ex_titles))
            subclause = (
                "NOT EXISTS ("
                "  SELECT 1 FROM recipe_tags te"
                "  WHERE te.url = s.url"
                "    AND te.category = ?"
                f"   AND te.title IN ({placeholders})"
                ")"
            )
            exclude_clauses.append(subclause)
            exclude_params.append(cat)
            exclude_params.extend(ex_titles)

    if exclude_clauses:
        where_parts.append(f"({' AND '.join(exclude_clauses)})")
    final_params.extend(exclude_params)

    if user_ingredients:
        placeholders = ",".join("?" * len(user_ingredients))
        where_parts.append(f"i.normalized_ingredient IN ({placeholders})")
        final_params.extend(user_ingredients)

    if forbidden_ingredients:
        forb_conditions = []
        for _ in forbidden_ingredients:
            forb_conditions.append(
                "fi.normalized_ingredient LIKE '%' || ? || '%' COLLATE NOCASE"
            )
        forb_clause = (
            "NOT EXISTS ("
            " SELECT 1 FROM recipe_ingredients fi"
            " WHERE fi.url=s.url AND (" + " OR ".join(forb_conditions) + ")"
            ")"
        )
        where_parts.append(f"({forb_clause})")
        final_params.extend(forbidden_ingredients)

    if must_use:
        for must in must_use:
            must_clause = (
                "EXISTS ("
                " SELECT 1 FROM recipe_ingredients mu"
                " WHERE mu.url = s.url"
                "   AND mu.normalized_ingredient LIKE '%' || ? || '%' COLLATE NOCASE"
                ")"
            )
            where_parts.append(must_clause)
            final_params.append(must)

    if keywords_to_include:
        for kw in keywords_to_include:
            incl_clause = (
                "("
                " s.title LIKE ? COLLATE NOCASE"
                "  OR s.description LIKE ? COLLATE NOCASE"
                "  OR EXISTS("
                "     SELECT 1 FROM recipe_ingredients i2"
                "     WHERE i2.url=s.url"
                "       AND i2.normalized_ingredient LIKE ? COLLATE NOCASE"
                "  )"
                ")"
            )
            where_parts.append(incl_clause)
            final_params.append(f"%{kw}%")
            final_params.append(f"%{kw}%")
            final_params.append(f"%{kw}%")

    if keywords_to_exclude:
        for kw in keywords_to_exclude:
            excl_clause = (
                "NOT ("
                " s.title LIKE ? COLLATE NOCASE"
                "  OR s.description LIKE ? COLLATE NOCASE"
                "  OR EXISTS("
                "     SELECT 1 FROM recipe_ingredients i2"
                "     WHERE i2.url=s.url"
                "       AND i2.normalized_ingredient LIKE ? COLLATE NOCASE"
                "  )"
                ")"
            )
            where_parts.append(excl_clause)
            final_params.append(f"%{kw}%")
            final_params.append(f"%{kw}%")
            final_params.append(f"%{kw}%")

    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    sql += " GROUP BY s.url\n"

    having_clauses = []
    if needed_tags_count > 0:
        if tag_filter_mode == "AND":
            having_clauses.append(f"matched_categories = {needed_tags_count}")
        else:
            having_clauses.append("matched_categories >= 1")

    if min_ing_matches > 0:
        having_clauses.append(f"matched_count >= {min_ing_matches}")

    if max_steps > 0:
        having_clauses.append(f"step_count <= {max_steps}")

    if having_clauses:
        sql += " HAVING " + " AND ".join(having_clauses)

    sql += " ORDER BY matched_count DESC\n"

    if limit > 0:
        sql += f" LIMIT {limit}"

    logging.info(f"Final SQL:\n{sql}")
    logging.info(f"Params: {final_params}")

    conn = get_db_connection()
    rows = conn.execute(sql, final_params).fetchall()
    conn.close()

    return [(r[0], r[1]) for r in rows]


def load_bulk_recipes(candidate_urls: list[str]) -> dict[str, dict]:
    """
    Load top-level, ingredients, instructions, and simplified_data
    for each url. Return a dict keyed by url.
    """
    if not candidate_urls:
        return {}

    placeholders = ",".join(["?"] * len(candidate_urls))

    query = f"""
        SELECT
            url,
            title,
            cook_time,
            yields,
            description,
            why_this_works,
            headnote,
            equipment,
            processed_at,
            course,
            main_ingredient
        FROM recipe_schema
        WHERE url IN ({placeholders})
        ORDER BY url
    """
    conn = get_db_connection()
    recipe_rows = conn.execute(query, candidate_urls).fetchall()
    conn.close()

    recipes = {}
    for row in recipe_rows:
        (
            url,
            title,
            cook_time,
            yields_,
            description,
            why_this_works,
            headnote,
            equipment,
            processed_at,
            course,
            main_ingredient,
        ) = row
        recipes[url] = {
            "url": url,
            "title": title or "",
            "cook_time": cook_time or "",
            "yields": yields_ or "",
            "description": description or "",
            "why_this_works": why_this_works or "",
            "headnote": headnote or "",
            "equipment": equipment or "",
            "processed_at": processed_at,
            "course": course,
            "main_ingredient": main_ingredient,
            "ingredients": [],
            "instructions": [],
            "simplified_data": {},
        }

    query_ing = f"""
        SELECT
            url,
            ingredient,
            normalized_ingredient,
            canonical_ingredient
        FROM recipe_ingredients
        WHERE url IN ({placeholders})
        ORDER BY url
    """
    conn = get_db_connection()
    ing_rows = conn.execute(query_ing, candidate_urls).fetchall()
    conn.close()

    for row in ing_rows:
        url, ingredient, norm_ing, can_ing = row
        if url in recipes:
            recipes[url]["ingredients"].append(
                {
                    "ingredient": ingredient,
                    "normalized_ingredient": norm_ing or "",
                    "canonical_ingredient": can_ing or "",
                }
            )

    query_instr = f"""
        SELECT
            url,
            step_number,
            instruction
        FROM recipe_instructions
        WHERE url IN ({placeholders})
        ORDER BY url, step_number
    """
    conn = get_db_connection()
    instr_rows = conn.execute(query_instr, candidate_urls).fetchall()
    conn.close()

    for row in instr_rows:
        url, step_number, instruction = row
        if url in recipes:
            recipes[url]["instructions"].append(
                {"step_number": step_number, "instruction": instruction}
            )

    query_simplified = f"""
        SELECT
            url,
            simplified_data
        FROM simplified_recipes
        WHERE url IN ({placeholders})
        ORDER BY url
    """
    conn = get_db_connection()
    simp_rows = conn.execute(query_simplified, candidate_urls).fetchall()
    conn.close()

    for row in simp_rows:
        url, simplified_data = row
        if url in recipes:
            try:
                recipes[url]["simplified_data"] = (
                    json.loads(simplified_data) if simplified_data else {}
                )
            except Exception as e:
                recipes[url]["simplified_data"] = {}
                logging.error(f"Error decoding simplified_data for {url}: {e}")

    return recipes


def bulk_compute_coverage(
    recipes_dict: dict[str, dict],
    user_ingredients: list[str],
    min_pair_sim: float = 0.9,
    alpha: float = 0.75,
    skip_hungarian_threshold: float = 0.3,
) -> list[tuple[str, str, float, float]]:
    """
    Batched coverage approach:
      - Gather all (canonical) ingredients in one big list & all raw ingredients in another.
      - Do one big cdist() for canonical and one for raw, then blend with alpha.
      - For each recipe sub-slice, perform a quick recipe coverage check.
          If the quick recipe coverage is below skip_hungarian_threshold, skip the Hungarian assignment.
          Otherwise, run the Hungarian algorithm and compute:
              * user_coverage: fraction of user ingredients that were matched (>0)
              * recipe_coverage: the average matched score over the recipe’s ingredients,
                which now reflects the granular (Hungarian) coverage.
    Returns a list of 4-tuples: (url, title, user_coverage, recipe_coverage).
    """

    if not user_ingredients:
        return [(u, rdata["title"], 0.0, 0.0) for (u, rdata) in recipes_dict.items()]

    all_canonical = []
    all_canonical_offsets = {}
    all_raw = []
    all_raw_offsets = {}
    offset_can = 0
    offset_raw = 0
    urls_sorted = sorted(recipes_dict.keys())
    for url in urls_sorted:
        rdata = recipes_dict[url]
        can_ings = [
            ing["canonical_ingredient"].lower().strip() for ing in rdata["ingredients"]
        ]
        raw_ings = [ing["ingredient"].lower().strip() for ing in rdata["ingredients"]]
        length_can = len(can_ings)
        length_raw = len(raw_ings)
        all_canonical_offsets[url] = (offset_can, offset_can + length_can)
        offset_can += length_can
        all_canonical.extend(can_ings)
        all_raw_offsets[url] = (offset_raw, offset_raw + length_raw)
        offset_raw += length_raw
        all_raw.extend(raw_ings)

    user_norm = [
        normalize_ingredient_name(get_canonical_ingredient(u)) for u in user_ingredients
    ]
    N = len(user_ingredients)
    sim_matrix_can_100 = cdist(
        user_norm, all_canonical, scorer=fuzz.token_set_ratio, workers=-1
    )
    sim_matrix_can = sim_matrix_can_100 / 100.0
    sim_matrix_raw_100 = cdist(
        user_ingredients, all_raw, scorer=fuzz.token_set_ratio, workers=-1
    )
    sim_matrix_raw = sim_matrix_raw_100 / 100.0
    combined_sim_matrix = alpha * sim_matrix_can + (1.0 - alpha) * sim_matrix_raw

    results = []
    for url in urls_sorted:
        rdata = recipes_dict[url]
        title = rdata["title"]
        (start_can, end_can) = all_canonical_offsets[url]
        M = end_can - start_can
        if M == 0:
            results.append((url, title, 0.0, 0.0))
            continue

        sim_sub = combined_sim_matrix[:, start_can:end_can]

        recipe_best_sims = np.max(sim_sub, axis=0)
        frac_recipe_covered = sum(1 for s in recipe_best_sims if s >= min_pair_sim) / M

        if frac_recipe_covered < skip_hungarian_threshold:
            user_best_sims = np.max(sim_sub, axis=1)
            frac_user_covered = sum(1 for s in user_best_sims if s >= min_pair_sim) / N

            results.append((url, title, frac_user_covered, frac_recipe_covered))
            continue

        sim_sub_copy = sim_sub.copy()
        sim_sub_copy[sim_sub_copy < min_pair_sim] = 0.0
        cost_matrix = 1.0 - sim_sub_copy
        max_dim = max(N, M)
        if N < max_dim:
            cost_matrix = np.vstack(
                [cost_matrix, np.ones((max_dim - N, M), dtype=cost_matrix.dtype)]
            )
        if M < max_dim:
            cost_matrix = np.hstack(
                [cost_matrix, np.ones((max_dim, max_dim - M), dtype=cost_matrix.dtype)]
            )
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matched_scores = []
        matched_columns = set()
        for r_idx, c_idx in zip(row_ind, col_ind):
            if r_idx < N and c_idx < M:
                val = sim_sub_copy[r_idx, c_idx]
                matched_scores.append(val)
                if val > 0.0:
                    matched_columns.add(c_idx)
            else:
                matched_scores.append(0.0)
        final_score = sum(matched_scores) / M
        matched_user = sum(1 for s in matched_scores if s > 0)
        user_coverage = matched_user / N

        results.append((url, title, user_coverage, final_score))
    return results


def query_top_k(
    user_ingredients: list[str],
    tag_filters: dict[str, list[str]],
    excluded_tags: dict[str, list[str]],
    min_ing_matches: int = 1,
    forbidden_ingredients: list[str] | None = None,
    tag_filter_mode: str = "OR",
    max_steps: int = 0,
    user_coverage_req: float = 0.0,
    recipe_coverage_req: float = 0.0,
    keywords_to_include: list[str] | None = None,
    keywords_to_exclude: list[str] | None = None,
    must_use: list[str] | None = None,
    sources: list[str] | None = None,
    top_n_db: int = 3000,
    skip_hungarian_threshold: float = 0.2,
):
    """
    1) Fetch up to 'top_n_db' candidate recipes.
    2) Compute fuzzy coverage (using bulk_compute_coverage) for each candidate.
    3) Filter results by user_coverage_req and recipe_coverage_req,
       then sort descending by recipe coverage then user coverage.
    4) Return a list of dicts with coverage metrics and full recipe data.
    """

    if forbidden_ingredients is None:
        forbidden_ingredients = []
    if must_use is None:
        must_use = []
    if keywords_to_include is None:
        keywords_to_include = []
    if keywords_to_exclude is None:
        keywords_to_exclude = []

    norm_user_ingredients = [
        normalize_ingredient_name(get_canonical_ingredient(u)) for u in user_ingredients
    ]
    norm_forbidden_ingredients = [
        normalize_ingredient_name(get_canonical_ingredient(u))
        for u in forbidden_ingredients
    ]
    norm_must_use = [
        normalize_ingredient_name(get_canonical_ingredient(u)) for u in must_use
    ]

    candidates = build_candidate_urls(
        tag_filters=tag_filters,
        excluded_tags=excluded_tags,
        user_ingredients=norm_user_ingredients,
        min_ing_matches=min_ing_matches,
        forbidden_ingredients=norm_forbidden_ingredients,
        must_use=norm_must_use,
        tag_filter_mode=tag_filter_mode,
        max_steps=max_steps,
        keywords_to_include=keywords_to_include,
        keywords_to_exclude=keywords_to_exclude,
        sources=sources,
        limit=top_n_db,
    )
    logging.info(f"Candidate set => {len(candidates)} from DB (limit={top_n_db})")
    if not candidates:
        return []
    candidate_urls = [c[0] for c in candidates]
    recipes_dict = load_bulk_recipes(candidate_urls)
    deduped_candidates = deduplicate_candidates(candidates, recipes_dict, threshold=95)
    if not deduped_candidates:
        candidates = build_candidate_urls(
            tag_filters=tag_filters,
            excluded_tags=excluded_tags,
            user_ingredients=norm_user_ingredients,
            min_ing_matches=min_ing_matches,
            forbidden_ingredients=norm_forbidden_ingredients,
            must_use=norm_must_use,
            tag_filter_mode=tag_filter_mode,
            max_steps=max_steps,
            keywords_to_include=keywords_to_include,
            keywords_to_exclude=keywords_to_exclude,
            sources=sources,
            limit=top_n_db * 2,
        )
        candidate_urls = [c[0] for c in candidates]
        recipes_dict = load_bulk_recipes(candidate_urls)
        deduped_candidates = deduplicate_candidates(
            candidates, recipes_dict, threshold=95
        )
    candidate_urls = [c[0] for c in deduped_candidates]
    recipes_dict = load_bulk_recipes(candidate_urls)

    cov_results = bulk_compute_coverage(
        recipes_dict=recipes_dict,
        user_ingredients=user_ingredients,
        min_pair_sim=0.9,
        alpha=0.75,
        skip_hungarian_threshold=skip_hungarian_threshold,
    )

    filtered = [
        (url, title, uc, rc)
        for (url, title, uc, rc) in cov_results
        if uc >= user_coverage_req and rc >= recipe_coverage_req
    ]
    df = pd.DataFrame(
        filtered, columns=["url", "title", "user_coverage", "recipe_coverage"]
    )
    df_sorted = df.sort_values(
        by=["recipe_coverage", "user_coverage"], ascending=[False, False]
    )

    final_results = []
    for row in df_sorted.itertuples(index=False):
        url, title, uc, rc = row
        final_results.append(
            {
                "url": url,
                "title": title,
                "user_coverage": uc,
                "recipe_coverage": rc,
                "matched_count": next(
                    (mcount for (u, mcount) in deduped_candidates if u == url), 0
                ),
                "recipe": recipes_dict.get(url, {}),
            }
        )
    return final_results
