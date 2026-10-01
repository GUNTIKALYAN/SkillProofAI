from typing import Dict, List
from app.utils.text_utils import normalize_text


class ATSVectorScorer:
    """
    Semantic skill matching using sentence embeddings.
    A JD skill is a semantic match when its best cosine similarity
    against any resume skill crosses the threshold.
    """

    def __init__(self, model_name: str = None, threshold: float = 0.55):
        if model_name is None:
            from app.config import SEMANTIC_MODEL_NAME
            model_name = SEMANTIC_MODEL_NAME

        self.model_name = model_name
        self.threshold = threshold
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def score(self, jd_skills: List[str], resume_skills: List[str]) -> Dict:
        jd_norm = [normalize_text(s) for s in jd_skills if s and s.strip()]
        rs_norm = [normalize_text(s) for s in resume_skills if s and s.strip()]

        if not jd_norm or not rs_norm:
            return {"similarities": {}, "matched": [], "match_rate": 0, "available": True}

        try:
            model = self._get_model()
        except (ImportError, OSError) as exc:
            print("SEMANTIC SCORER UNAVAILABLE:", exc)
            return {
                "similarities": {},
                "matched": [],
                "match_rate": None,
                "available": False,
            }

        jd_emb = model.encode(jd_norm, normalize_embeddings=True)
        rs_emb = model.encode(rs_norm, normalize_embeddings=True)

        sim_matrix = jd_emb @ rs_emb.T

        similarities = {}
        matched = []

        for i, skill in enumerate(jd_norm):
            best = float(sim_matrix[i].max())
            similarities[skill] = round(best, 4)
            if best >= self.threshold:
                matched.append(skill)

        match_rate = (
            int((len(matched) / len(jd_norm)) * 100) if jd_norm else 0
        )

        return {
            "similarities": similarities,
            "matched": matched,
            "match_rate": match_rate,
            "available": True,
        }
