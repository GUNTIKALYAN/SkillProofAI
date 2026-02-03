from app.core.ats_bm25 import ATSBM25Scorer

def compute_ats_score(jd_skills, resume_skills, missing_skills):
    bm25 = ATSBM25Scorer(jd_skills)
    bm25_result = bm25.score(resume_skills)

    raw_scores = bm25_result["raw_scores"]

    # 🔑 KEY FIX: count matched JD skills
    matched_keywords = sum(1 for s in raw_scores if s > 0)

    total_keywords = len(jd_skills)

    keyword_match_rate = (
        int((matched_keywords / total_keywords) * 100)
        if total_keywords > 0 else 0
    )

    # 🔍 DEBUG (keep for now)
    print("BM25 RAW SCORES:", raw_scores)
    print("MATCHED KEYWORDS:", matched_keywords)
    print("KEYWORD MATCH RATE:", keyword_match_rate)

    return {
        "keyword_match_rate": keyword_match_rate,
        "matched_keywords": matched_keywords,
        "total_keywords": total_keywords,
        "bm25_raw": bm25_result,
        "missing_skill_count": len(missing_skills)
    }
