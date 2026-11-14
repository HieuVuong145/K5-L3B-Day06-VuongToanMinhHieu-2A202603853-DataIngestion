"""Implement fixed-size and structure-aware chunking."""
import uuid
from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split text into overlapping fixed-size windows and retain page metadata (Strategy A)."""
    text = page.text
    if not text:
        return []
        
    chunks: list[Chunk] = []
    start = 0
    chunk_index = 0
    
    while start < len(text):
        end = min(start + size, len(text))
        chunk_text = text[start:end].strip()
        
        if chunk_text:
            chunk_id = f"A_{page.document_id}_p{page.page}_c{chunk_index}"
            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata={
                    "strategy": "A",
                    "chapter": page.metadata.get("chapter", "Unknown"),
                    "chunk_index": chunk_index,
                    "char_start": start,
                    "char_end": end
                }
            )
            chunks.append(chunk)
            chunk_index += 1
            
        if end == len(text):
            break
        start += max(1, size - overlap)
        
    return chunks


def by_paragraph(page: DocumentPage, max_size: int = 800) -> list[Chunk]:
    """Structure-aware chunking: group natural paragraphs and respect thought boundaries (Strategy B & C)."""
    text = page.text
    if not text:
        return []
        
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    current_group: list[str] = []
    current_len = 0
    chunk_index = 0
    
    for para in paragraphs:
        # Nếu đoạn văn đơn lẻ vượt quá max_size, chia nhỏ theo câu
        if len(para) > max_size:
            # Nếu đang có nhóm đoạn trước đó, xuất ra thành chunk trước
            if current_group:
                grouped_text = "\n\n".join(current_group)
                chunk_id = f"B_{page.document_id}_p{page.page}_c{chunk_index}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=grouped_text,
                    metadata={
                        "strategy": "B_or_C",
                        "chapter": page.metadata.get("chapter", "Unknown"),
                        "chunk_index": chunk_index
                    }
                ))
                chunk_index += 1
                current_group = []
                current_len = 0
                
            # Chia nhỏ đoạn quá dài
            sub_start = 0
            while sub_start < len(para):
                sub_end = min(sub_start + max_size, len(para))
                sub_text = para[sub_start:sub_end].strip()
                if sub_text:
                    chunk_id = f"B_{page.document_id}_p{page.page}_c{chunk_index}"
                    chunks.append(Chunk(
                        chunk_id=chunk_id,
                        document_id=page.document_id,
                        source=page.source,
                        page=page.page,
                        text=sub_text,
                        metadata={
                            "strategy": "B_or_C",
                            "chapter": page.metadata.get("chapter", "Unknown"),
                            "chunk_index": chunk_index
                        }
                    ))
                    chunk_index += 1
                sub_start += max(1, max_size - 50)
            continue

        # Nếu thêm para này không vượt quá max_size
        if current_len + len(para) + 2 <= max_size:
            current_group.append(para)
            current_len += len(para) + 2
        else:
            # Xuất nhóm hiện tại
            if current_group:
                grouped_text = "\n\n".join(current_group)
                chunk_id = f"B_{page.document_id}_p{page.page}_c{chunk_index}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=grouped_text,
                    metadata={
                        "strategy": "B_or_C",
                        "chapter": page.metadata.get("chapter", "Unknown"),
                        "chunk_index": chunk_index
                    }
                ))
                chunk_index += 1
            current_group = [para]
            current_len = len(para)

    # Đóng nốt nhóm còn lại
    if current_group:
        grouped_text = "\n\n".join(current_group)
        chunk_id = f"B_{page.document_id}_p{page.page}_c{chunk_index}"
        chunks.append(Chunk(
            chunk_id=chunk_id,
            document_id=page.document_id,
            source=page.source,
            page=page.page,
            text=grouped_text,
            metadata={
                "strategy": "B_or_C",
                "chapter": page.metadata.get("chapter", "Unknown"),
                "chunk_index": chunk_index
            }
        ))
        
    return chunks
