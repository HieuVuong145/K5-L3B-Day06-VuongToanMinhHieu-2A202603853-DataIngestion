"""Evaluate retrieved evidence and preserve per-query traces."""
from typing import Any


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and evidence match; record Hit@1 and Hit@3 flags."""
    gold_page = question["gold_page"]
    evidence_quote = question.get("evidence_quote", "").lower().strip()
    
    # Tách các cụm từ khóa chính để so khớp linh hoạt
    # Nếu câu dài, chỉ cần một cụm mang ý nghĩa bằng chứng cốt lõi xuất hiện là đạt
    raw_phrases = [p.strip() for p in evidence_quote.replace("...", ",").split(",") if len(p.strip()) >= 5]
    if not raw_phrases:
        raw_phrases = [evidence_quote]
        
    hit_at_1 = False
    hit_at_3 = False
    matched_rank = None
    matched_chunk_id = None
    
    for rank, hit in enumerate(hits, start=1):
        chunk_page = hit.get("page")
        chunk_text = hit.get("text", "").lower()
        
        # Điều kiện Hit: Đúng trang (cho phép sai số 1 trang do ngắt trang PDF)
        # VÀ chứa toàn bộ evidence_quote HOẶC ít nhất 1 cụm bằng chứng cốt lõi
        page_match = (chunk_page == gold_page or abs(chunk_page - gold_page) <= 1)
        full_match = evidence_quote in chunk_text if evidence_quote else False
        phrase_match = any(kp in chunk_text for kp in raw_phrases) if raw_phrases else False
        
        if page_match and (full_match or phrase_match):
            if rank == 1:
                hit_at_1 = True
            hit_at_3 = True
            if matched_rank is None:
                matched_rank = rank
                matched_chunk_id = hit.get("chunk_id")
            break
            
    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "gold_page": gold_page,
        "evidence_quote": question.get("evidence_quote"),
        "filter_used": question.get("filter"),
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "matched_rank": matched_rank,
        "matched_chunk_id": matched_chunk_id,
        "hits": hits
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by dev/test split."""
    dev_traces = [t for t in traces if t["split"] == "dev"]
    test_traces = [t for t in traces if t["split"] == "test"]
    
    def calc_metrics(sub_traces: list[dict[str, Any]]):
        total = len(sub_traces)
        if total == 0:
            return {"hit1": "0/0", "hit1_pct": 0.0, "hit3": "0/0", "hit3_pct": 0.0, "total": 0}
        h1 = sum(1 for t in sub_traces if t["hit_at_1"])
        h3 = sum(1 for t in sub_traces if t["hit_at_3"])
        return {
            "hit1": f"{h1}/{total}",
            "hit1_pct": round(h1 / total * 100, 2),
            "hit3": f"{h3}/{total}",
            "hit3_pct": round(h3 / total * 100, 2),
            "total": total
        }
        
    return {
        "dev": calc_metrics(dev_traces),
        "test": calc_metrics(test_traces),
        "all": calc_metrics(traces)
    }
