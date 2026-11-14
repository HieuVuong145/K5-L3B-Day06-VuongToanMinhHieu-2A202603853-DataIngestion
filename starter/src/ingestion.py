"""Read and normalize Vietnamese university academic regulation PDF data."""
import re
import unicodedata
import urllib.request
from pathlib import Path
import pypdf

from .models import DocumentPage

OFFICIAL_PDF_URL = "https://ctt.hust.edu.vn/Upload/Nguy%E1%BB%85n%20Qu%E1%BB%91c%20%C4%90%E1%BA%A1t/files/DTDH_QDQC/Hoctap/QCDT_2025_5445_QD-DHBK.pdf"


def ensure_pdf(path: Path, url: str = OFFICIAL_PDF_URL) -> Path:
    """Ensure the PDF file exists locally; if not, automatically download from official URL."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[Ingestion] Local PDF not found at {path.name}. Downloading from official URL:\n  {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(path, "wb") as f:
            f.write(resp.read())
        print(f"[Ingestion] Download complete ({path.stat().st_size} bytes saved to {path.name}).")
    return path


def normalize_text(text: str) -> str:
    """Normalize Vietnamese Unicode (NFC) and formatting whitespaces.
    
    Preserves meaningful paragraph/clause breaks while cleaning OCR/PDF artifacts.
    """
    if not text:
        return ""
    # Chuẩn hóa Unicode dạng chuẩn NFC
    text = unicodedata.normalize("NFC", text)
    # Thay thế tabs bằng khoảng trắng
    text = text.replace("\t", " ")
    
    lines = [re.sub(r"[ \xa0]+", " ", line).strip() for line in text.split("\n")]
    
    # Gom các dòng thuộc cùng một đoạn/khoản
    paragraphs: list[str] = []
    current_para: list[str] = []
    
    for line in lines:
        if not line:
            if current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []
        elif re.match(r"^(CHƯƠNG\s+[IVXLCDM]+|Điều\s+\d+\.|\d+\.|\w\))", line):
            if current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []
            current_para.append(line)
        else:
            current_para.append(line)
            
    if current_para:
        paragraphs.append(" ".join(current_para))
        
    return "\n\n".join(paragraphs)


def load_pdf(path: Path, document_id: str, source: str = OFFICIAL_PDF_URL, start_page: int = 5, end_page: int = 34) -> list[DocumentPage]:
    """Extract physical content pages (pages 5 to 34); keep page numbers and chapter metadata.
    
    Pages 2-4 (cover and TOC) are excluded as required by GUIDE.md.
    If the PDF is not found locally, automatically downloads from the official URL.
    """
    ensure_pdf(path, url=source if source.startswith("http") else OFFICIAL_PDF_URL)
    reader = pypdf.PdfReader(str(path))
    pages: list[DocumentPage] = []
    
    current_chapter = "Chương I"
    chapter_titles = {
        "I": "Chương I: Những quy định chung",
        "II": "Chương II: Quy định đào tạo trình độ đại học",
        "III": "Chương III: Quy định đào tạo chương trình kỹ sư chuyên sâu",
        "IV": "Chương IV: Quy định đào tạo trình độ thạc sĩ",
        "V": "Chương V: Quy định đào tạo trình độ tiến sĩ",
        "VI": "Chương VI: Tổ chức thực hiện"
    }
    
    total_physical = len(reader.pages)
    start_idx = max(0, start_page - 1)
    end_idx = min(total_physical, end_page)

    for idx in range(start_idx, end_idx):
        physical_page = idx + 1
        raw_text = reader.pages[idx].extract_text() or ""
        
        # Nhận diện chương mới nếu có trong trang
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        for line in lines:
            match = re.search(r"CHƯƠNG\s+([IVXLCDM]+)", line)
            if match:
                ch_roman = match.group(1)
                current_chapter = chapter_titles.get(ch_roman, f"Chương {ch_roman}")
                break

        norm_text = normalize_text(raw_text)
        if not norm_text:
            continue
            
        doc_page = DocumentPage(
            document_id=document_id,
            source=source,
            page=physical_page,
            text=norm_text,
            metadata={
                "chapter": current_chapter,
                "length": len(norm_text)
            }
        )
        pages.append(doc_page)
        
    return pages
