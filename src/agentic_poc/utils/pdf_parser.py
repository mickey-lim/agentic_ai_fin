import pathlib
import os
import pandas as pd
import pdfplumber

class PdfParsingError(Exception):
    """Exception raised when a PDF cannot be parsed into a structured dataframe."""
    pass

def parse_pdf_to_dataframe(file_path: str, max_pages: int = 10, max_size_mb: int = 10) -> pd.DataFrame:
    """
    Parse a text-based PDF using pdfplumber to extract tables into a pd.DataFrame.
    Fails if the file exceeds constraints or contains no valid tables.
    """
    path = pathlib.Path(file_path)
    
    # 1. 파일 크기 검증 (Fallback validation)
    if path.exists() and os.path.getsize(path) > max_size_mb * 1024 * 1024:
        raise PdfParsingError(f"PDF 파일 사이즈가 {max_size_mb}MB를 초과합니다.")
        
    try:
        with pdfplumber.open(file_path) as pdf:
            # 2. 페이지 수 검증
            if len(pdf.pages) > max_pages:
                raise PdfParsingError(f"PDF 파일 페이지 수가 {max_pages}장을 초과합니다.")
                
            all_rows = []
            headers = None
            
            for page in pdf.pages:
                # Basic table extraction strategy
                tables = page.extract_tables()
                if not tables:
                    continue
                    
                for table in tables:
                    if not table:
                        continue
                    # Assume first row of the first valid table could be headers
                    # Or we just aggregate everything
                    if headers is None and len(table) > 1:
                        headers = table[0]
                        all_rows.extend(table[1:])
                    else:
                        # Append assuming same structure or just raw rows
                        all_rows.extend(table)
                        
            if not all_rows:
                raise PdfParsingError("지원되지 않는 PDF 레이아웃 (표 구조를 찾을 수 없습니다)")
                
            # If headers couldn't be cleanly determined, use generic columns
            if headers:
                # Fill missing headers with generic names
                clean_headers = [h if h else f"col_{i}" for i, h in enumerate(headers)]
                # Ensure all rows have the same length as headers
                clean_rows = [row[:len(clean_headers)] + [None] * (len(clean_headers) - len(row)) for row in all_rows]
                df = pd.DataFrame(clean_rows, columns=clean_headers)
            else:
                df = pd.DataFrame(all_rows)
                
            df.attrs["parser_type"] = "pdf_text"
            return df
            
    except PdfParsingError:
        raise
    except Exception as e:
        raise PdfParsingError(f"지원되지 않는 PDF 레이아웃 ({str(e)})")
