"""Main orchestration for the Day 06 Data Ingestion & Retrieval Benchmark using OpenRouter API."""
import csv
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

from .models import DocumentPage
from .ingestion import load_pdf, OFFICIAL_PDF_URL
from .chunking import fixed_size, by_paragraph
from .embeddings import OpenRouterEmbedder
from .store import PgVectorStore
from .evaluation import evaluate_query, summarize


class TeeLogger:
    """Tee stdout to both console and a log file."""
    def __init__(self, filepath: Path) -> None:
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")

    def write(self, message: str) -> None:
        self.terminal.write(message)
        self.log.write(message)

    def flush(self) -> None:
        self.terminal.flush()
        self.log.flush()


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    starter_dir = Path(__file__).resolve().parents[1]
    
    # Load environment variables
    load_dotenv(starter_dir / ".env")
    db_url = os.getenv("DATABASE_URL", "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab")
    model_name = os.getenv("EMBEDDING_MODEL") or "openai/text-embedding-3-small"
    
    pdf_path = repo_root / "QCDT_2025_5445_QD-DHBK.pdf"
    benchmark_path = repo_root / "benchmark" / "benchmark.json"
    results_dir = repo_root / "results"
    artifacts_dir = repo_root / "artifacts"
    data_dir = repo_root / "data"
    
    results_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Tee execution logs directly into results/pipeline.log
    sys.stdout = TeeLogger(results_dir / "pipeline.log")
    
    print("=" * 60)
    print("DAY 06 · DATA INGESTION ENGINEERING BENCHMARK (OPENROUTER API)")
    print("=" * 60)
    
    # 1. Load benchmark
    print(f"\n[1/5] Loading benchmark from {benchmark_path.relative_to(repo_root)}...")
    with open(benchmark_path, "r", encoding="utf-8") as f:
        questions = json.load(f)
    print(f"Loaded {len(questions)} questions ({sum(1 for q in questions if q['split'] == 'dev')} dev, {sum(1 for q in questions if q['split'] == 'test')} test).")
    
    # 2. Ingestion: Load pages from PDF
    cache_path = data_dir / "extracted_pages_cache_dhbk.json"
    t0_ingest = time.time()
    
    print(f"\n[2/5] Ingesting PDF from {OFFICIAL_PDF_URL} (pages 5 to 34)...")
    pages = load_pdf(pdf_path, document_id="quy_che_dao_tao_dhbk_2025", source=OFFICIAL_PDF_URL, start_page=5, end_page=34)
    ingest_duration = round(time.time() - t0_ingest, 2)
    print(f"Loaded {len(pages)} content pages from PDF in {ingest_duration}s.")
    
    # Save cache
    cache_data = [
        {
            "document_id": p.document_id,
            "source": p.source,
            "page": p.page,
            "text": p.text,
            "metadata": p.metadata
        }
        for p in pages
    ]
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print(f"Saved extraction cache to {cache_path.name}.")
    
    # 3. Chunking: Generate chunks for Strategy A & B
    print("\n[3/5] Generating chunks for Strategies A and B...")
    t0_chunk = time.time()
    chunks_a = []
    for p in pages:
        chunks_a.extend(fixed_size(p, size=500, overlap=50))
        
    chunks_b = []
    for p in pages:
        chunks_b.extend(by_paragraph(p, max_size=800))
        
    chunk_duration = round(time.time() - t0_chunk, 2)
    print(f"Strategy A (Fixed-size 500, overlap 50): {len(chunks_a)} chunks")
    print(f"Strategy B (Paragraph/structure, max 800): {len(chunks_b)} chunks")
    print(f"Chunking completed in {chunk_duration}s.")
    
    # 4. Embeddings & Storage via OpenRouter
    print(f"\n[4/5] Initializing OpenRouter Embedder ({model_name})...")
    embedder = OpenRouterEmbedder(model_name=model_name)
    store = PgVectorStore(db_url, dimensions=embedder.dimensions)
    store.create_schema()
    
    # Embed & Upsert Strategy A
    print(f"\nEmbedding & Storing Strategy A ({len(chunks_a)} chunks via OpenRouter)...")
    t0_a = time.time()
    texts_a = [c.text for c in chunks_a]
    vectors_a = embedder.embed_documents(texts_a, batch_size=32)
    store.upsert(strategy="A", chunks=chunks_a, vectors=vectors_a, batch_size=100)
    duration_a = round(time.time() - t0_a, 2)
    print(f"Strategy A stored in {duration_a}s.")
    
    # Embed & Upsert Strategy B
    print(f"\nEmbedding & Storing Strategy B ({len(chunks_b)} chunks via OpenRouter)...")
    t0_b = time.time()
    texts_b = [c.text for c in chunks_b]
    vectors_b = embedder.embed_documents(texts_b, batch_size=32)
    store.upsert(strategy="B", chunks=chunks_b, vectors=vectors_b, batch_size=100)
    duration_b = round(time.time() - t0_b, 2)
    print(f"Strategy B stored in {duration_b}s.")
    
    # 5. Run Benchmark on Strategy A, B, and C
    print("\n[5/5] Running Retrieval Benchmark for Strategies A, B, and C...")
    strategies = ["A", "B", "C"]
    all_summaries = {}
    
    for strat in strategies:
        print(f"\nEvaluating Strategy {strat}...")
        traces = []
        for q in questions:
            # Query vector
            q_vec = embedder.embed_query(q["question"])
            
            # Cấu hình C: áp dụng metadata filter khi câu hỏi yêu cầu filter
            # Cấu hình A & B: không áp dụng filter
            target_store_strat = "B" if strat == "C" else strat
            active_filter = q.get("filter") if strat == "C" else None
            
            hits = store.search(
                strategy=target_store_strat,
                query_vector=q_vec,
                top_k=3,
                filters=active_filter
            )
            
            trace = evaluate_query(q, hits)
            trace["strategy"] = strat
            traces.append(trace)
            
        summary = summarize(traces)
        all_summaries[strat] = summary
        
        # Lưu trace chi tiết
        trace_file = results_dir / f"traces_{strat}.json"
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(traces, f, ensure_ascii=False, indent=2)
        print(f"Saved traces to {trace_file.relative_to(repo_root)}")
        print(f"Strategy {strat} -> Dev Hit@1: {summary['dev']['hit1']} ({summary['dev']['hit1_pct']}%) | Dev Hit@3: {summary['dev']['hit3']} ({summary['dev']['hit3_pct']}%)")
        print(f"Strategy {strat} -> Test Hit@1: {summary['test']['hit1']} ({summary['test']['hit1_pct']}%) | Test Hit@3: {summary['test']['hit3']} ({summary['test']['hit3_pct']}%)")

    # Tính toán chi phí OpenRouter: $0.02 / 1M tokens đối với text-embedding-3-small
    total_tokens = embedder.total_tokens_used
    estimated_cost = round(total_tokens * (0.02 / 1_000_000), 5)
    print(f"\nTotal Tokens used: {total_tokens} | Estimated OpenRouter API Cost: ${estimated_cost:.5f}")

    # Lưu summary tổng hợp
    all_summaries["usage"] = {
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost,
        "model": model_name
    }
    summary_file = results_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, ensure_ascii=False, indent=2)
    print(f"Saved overall summary to {summary_file.relative_to(repo_root)}")
    
    # Cập nhật artifacts/experiment_log.csv
    exp_log_file = artifacts_dir / "experiment_log.csv"
    with open(exp_log_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "chunking", "chunk_size", "overlap", "metadata", "filter", "vectorizer", "hypothesis", "dev_hit1", "dev_hit3", "test_hit1", "test_hit3", "notes"])
        writer.writerow([
            "A", "fixed_size", 500, 50, "doc_id,source,page", "none", model_name,
            "Cắt cố định dễ làm cụt điều khoản pháp lý, giảm độ mạch lạc và Hit@3",
            all_summaries["A"]["dev"]["hit1"], all_summaries["A"]["dev"]["hit3"],
            all_summaries["A"]["test"]["hit1"], all_summaries["A"]["test"]["hit3"],
            f"{len(chunks_a)} chunks, {duration_a}s, cost ~${estimated_cost/2:.5f}"
        ])
        writer.writerow([
            "B", "by_paragraph", 800, 0, "doc_id,source,page,chapter", "none", model_name,
            "Cắt theo đoạn/khoản giữ trọn vẹn ngữ nghĩa điều luật, tăng Hit@1 và Hit@3",
            all_summaries["B"]["dev"]["hit1"], all_summaries["B"]["dev"]["hit3"],
            all_summaries["B"]["test"]["hit1"], all_summaries["B"]["test"]["hit3"],
            f"{len(chunks_b)} chunks, {duration_b}s, cost ~${estimated_cost/2:.5f}"
        ])
        writer.writerow([
            "C", "by_paragraph", 800, 0, "doc_id,source,page,chapter", "chapter_filter", model_name,
            "Lọc theo chương giúp khu biệt đúng phạm vi đối tượng (đại học/thạc sĩ/kỹ sư)",
            all_summaries["C"]["dev"]["hit1"], all_summaries["C"]["dev"]["hit3"],
            all_summaries["C"]["test"]["hit1"], all_summaries["C"]["test"]["hit3"],
            f"Tận dụng index B + SQL filter, chi phí tối ưu"
        ])
    print(f"Updated {exp_log_file.relative_to(repo_root)}")

    # In bảng so sánh tổng kết
    print("\n" + "=" * 75)
    print("FINAL BENCHMARK RESULTS (DHBK ACADEMIC REGULATION)")
    print("=" * 75)
    print(f"{'Strategy':<10} | {'Split':<6} | {'Hit@1 (n/N)':<12} | {'Hit@3 (n/N)':<12} | {'Chunks':<8} | {'Cost'}")
    print("-" * 75)
    for strat in ["A", "B", "C"]:
        cnt = len(chunks_a) if strat == "A" else len(chunks_b)
        cost_str = f"${estimated_cost:.5f}"
        print(f"{strat:<10} | {'dev':<6} | {all_summaries[strat]['dev']['hit1']:<12} | {all_summaries[strat]['dev']['hit3']:<12} | {cnt:<8} | {cost_str}")
        print(f"{strat:<10} | {'test':<6} | {all_summaries[strat]['test']['hit1']:<12} | {all_summaries[strat]['test']['hit3']:<12} | {cnt:<8} | {cost_str}")
        print("-" * 75)


if __name__ == "__main__":
    main()
