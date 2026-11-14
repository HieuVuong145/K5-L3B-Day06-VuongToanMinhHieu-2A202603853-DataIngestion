"""OpenRouter Embedding provider adapter using openai/text-embedding-3-small."""
import json
import os
import time
import urllib.request
from typing import Protocol
from dotenv import load_dotenv


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, question: str) -> list[float]:
        ...


class OpenRouterEmbedder:
    """Production-grade embedding adapter using OpenRouter API."""

    def __init__(self, model_name: str = "openai/text-embedding-3-small", api_key: str | None = None) -> None:
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is missing in environment or starter/.env.")
            
        self.endpoint = "https://openrouter.ai/api/v1/embeddings"
        self.dimensions = 1536  # Chuẩn dimension của text-embedding-3-small
        self.total_tokens_used = 0
        
        # Test connection & verify dimensions
        print(f"[Embedder] Verifying OpenRouter connection with model '{self.model_name}'...")
        test_vec = self.embed_query("Kiểm tra kết nối OpenRouter")
        self.dimensions = len(test_vec)
        print(f"[Embedder] Ready! Verified dimensions: {self.dimensions}")

    def _call_api(self, inputs: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = json.dumps({
            "model": self.model_name,
            "input": inputs
        }).encode("utf-8")
        
        req = urllib.request.Request(self.endpoint, data=payload, headers=headers, method="POST")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    
                    # Cập nhật usage tokens nếu có
                    usage = resp_data.get("usage", {})
                    self.total_tokens_used += usage.get("total_tokens", 0)
                    
                    # Sắp xếp theo index và ép kiểu float đồng nhất để tránh lỗi mixed types trong psycopg
                    data_items = sorted(resp_data["data"], key=lambda x: x["index"])
                    return [[float(x) for x in item["embedding"]] for item in data_items]
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"OpenRouter API call failed after 3 attempts: {e}")
                time.sleep(2 ** attempt)
        return []

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self._call_api(batch)
            all_embeddings.extend(embeddings)
            time.sleep(0.1)  # Rate-limit safety
        return all_embeddings

    def embed_query(self, question: str) -> list[float]:
        res = self._call_api([question])
        return res[0]
