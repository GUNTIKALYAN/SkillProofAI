from app.core.ats_bm25 import ATSBM25Scorer
from app.core.ats_vector import ATSVectorScorer
from app.config import SEMANTIC_MATCH_THRESHOLD


def compute_ats_score(jd_skills, resume_skills, missing_skills):
    # -------------------------
    # 1. BM25 lexical scoring
    # -------------------------
    bm25 = ATSBM25Scorer(jd_skills)
    bm25_result = bm25.score(resume_skills)

    raw_scores = bm25_result["raw_scores"]
    normalized_jd = bm25.jd_skills

    bm25_matched = {
        skill
        for skill, score in zip(normalized_jd, raw_scores)
        if score > 0
    }

    # -------------------------
    # 2. Vector (semantic) scoring
    # -------------------------
    vector = ATSVectorScorer(threshold=SEMANTIC_MATCH_THRESHOLD)
    vector_result = vector.score(normalized_jd, resume_skills)

    semantic_available = vector_result.get("available", True)
    semantic_matched = set(vector_result["matched"]) if semantic_available else set()

    # -------------------------
    # 3. Hybrid fusion
    # -------------------------
    hybrid_matched = bm25_matched | semantic_matched

    total_keywords = len(set(normalized_jd))

    keyword_match_rate = (
        int((len(hybrid_matched) / total_keywords) * 100)
        if total_keywords > 0 else 0
    )

    bm25_match_rate = (
        int((len(bm25_matched) / total_keywords) * 100)
        if total_keywords > 0 else 0
    )

    print("BM25 MATCHED:", sorted(bm25_matched))
    print("SEMANTIC MATCHED:", sorted(semantic_matched))
    print("HYBRID MATCH RATE:", keyword_match_rate)

    return {
        "keyword_match_rate": keyword_match_rate,
        "matched_keywords": len(hybrid_matched),
        "total_keywords": total_keywords,
        "bm25_raw": bm25_result,
        "bm25_match_rate": bm25_match_rate,
        "semantic_similarities": vector_result["similarities"],
        "semantic_match_rate": vector_result["match_rate"],
        "semantic_available": semantic_available,
        "hybrid_matched_skills": sorted(hybrid_matched),
        "missing_skill_count": len(missing_skills)
    }
