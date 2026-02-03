from typing import List, Dict
import numpy as np
from rank_bm25 import BM25Okapi
from app.utils.text_utils import normalize_text


class ATSBM25Scorer:
    def __init__(self, jd_skills: List[str]):
        # Defensive programming
        self.jd_skills = [
            normalize_text(s) for s in jd_skills if s and s.strip()
        ]

        if not self.jd_skills:
            self.bm25 = None
            self.corpus = []
            return

        self.corpus = [skill.split() for skill in self.jd_skills]
        self.bm25 = BM25Okapi(self.corpus)

    def score(self, resume_skills: List[str]) -> Dict:
        if not self.bm25 or not resume_skills:
            return {
                "raw_scores": [],
                "avg_score": 0.0,
                "max_score": 0.0
            }

        resume_tokens = []
        for skill in resume_skills:
            if skill and skill.strip():
                resume_tokens.extend(normalize_text(skill).split())

        if not resume_tokens:
            return {
                "raw_scores": [],
                "avg_score": 0.0,
                "max_score": 0.0
            }

        scores = np.array(self.bm25.get_scores(resume_tokens))

        return {
            "raw_scores": scores.tolist(),
            "avg_score": float(scores.mean()),
            "max_score": float(scores.max())
        }
