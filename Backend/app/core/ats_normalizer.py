def bm25_to_percentage(avg_score: float, max_score: float) -> int:
    if max_score <= 0:
        return 0

    percentage = (avg_score / max_score) * 100

    # Clamp to [0, 100]
    return max(0, min(100, round(percentage)))
