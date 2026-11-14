"""Store and search vectors using PostgreSQL + pgvector with idempotency and metadata filtering."""
import json
from typing import Any
import psycopg
from pgvector.psycopg import register_vector

from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int = 1536) -> None:
        self.database_url = database_url
        self.dimensions = dimensions

    def _get_connection(self):
        conn = psycopg.connect(self.database_url)
        register_vector(conn)
        return conn

    def create_schema(self) -> None:
        """Ensure pgvector extension is enabled and create chunks table with matching dimensions."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                
                # Kiểm tra nếu bảng đã tồn tại thì kiểm tra dimension
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'chunks'
                    );
                """)
                table_exists = cur.fetchone()[0]
                if table_exists:
                    cur.execute("""
                        SELECT atttypmod 
                        FROM pg_attribute 
                        WHERE attrelid = 'chunks'::regclass AND attname = 'embedding';
                    """)
                    row = cur.fetchone()
                    if row and row[0] != self.dimensions:
                        print(f"[Store] Dropping obsolete table (dimension {row[0]} != target {self.dimensions})...")
                        cur.execute("DROP TABLE IF EXISTS chunks;")
                
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS chunks (
                        chunk_id TEXT PRIMARY KEY,
                        strategy TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        chapter TEXT,
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL,
                        embedding vector({self.dimensions})
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_strategy ON chunks (strategy);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chapter ON chunks (chapter);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks (page);")
            conn.commit()
        print(f"[Store] Schema initialized with {self.dimensions} dimensions.")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]], batch_size: int = 200) -> None:
        """Idempotent batch insert/update to prevent duplicate records on re-run."""
        if len(chunks) != len(vectors):
            raise ValueError(f"Length mismatch: {len(chunks)} chunks vs {len(vectors)} vectors")
            
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(chunks), batch_size):
                    batch_c = chunks[i:i + batch_size]
                    batch_v = vectors[i:i + batch_size]
                    
                    data = []
                    for c, v in zip(batch_c, batch_v):
                        chapter = c.metadata.get("chapter", "Unknown")
                        data.append((
                            c.chunk_id,
                            strategy,
                            c.document_id,
                            c.source,
                            c.page,
                            chapter,
                            c.text,
                            json.dumps(c.metadata),
                            [float(x) for x in v]
                        ))
                    
                    cur.executemany("""
                        INSERT INTO chunks (chunk_id, strategy, document_id, source, page, chapter, text, metadata, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            strategy = EXCLUDED.strategy,
                            document_id = EXCLUDED.document_id,
                            source = EXCLUDED.source,
                            page = EXCLUDED.page,
                            chapter = EXCLUDED.chapter,
                            text = EXCLUDED.text,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding;
                    """, data)
            conn.commit()
        print(f"[Store] Upserted {len(chunks)} chunks for strategy {strategy} successfully.")

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Rank by cosine similarity with strategy and optional metadata filtering."""
        query_vector = [float(x) for x in query_vector]
        where_clauses = ["strategy = %s"]
        params: list[Any] = [strategy]
        
        # Áp dụng bộ lọc metadata nếu có (ví dụ lọc theo chapter)
        if filters:
            if "chapter" in filters and filters["chapter"]:
                # Cho phép substring match hoặc exact match
                where_clauses.append("chapter ILIKE %s")
                params.append(f"%{filters['chapter']}%")
            if "page" in filters and filters["page"] is not None:
                where_clauses.append("page = %s")
                params.append(filters["page"])
                
        where_sql = " AND ".join(where_clauses)
        
        full_sql = f"""
            SELECT chunk_id, document_id, source, page, chapter, text, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """
        sql_params = [query_vector] + params + [query_vector, top_k]

        results = []
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(full_sql, sql_params)
                rows = cur.fetchall()
                for row in rows:
                    results.append({
                        "chunk_id": row[0],
                        "document_id": row[1],
                        "source": row[2],
                        "page": row[3],
                        "chapter": row[4],
                        "text": row[5],
                        "metadata": row[6],
                        "score": float(row[7])
                    })
        return results
