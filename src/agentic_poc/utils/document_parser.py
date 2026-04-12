import pathlib
import os
import pandas as pd
import pdfplumber
import io

class DocumentParsingError(Exception):
    """Exception raised when a document cannot be parsed into a structured dataframe."""
    pass

def _parse_image_vlm(file_path: str) -> pd.DataFrame:
    from src.agentic_poc.utils.vlm_extractor import extract_via_vlm
    path = pathlib.Path(file_path)
    mime = "image/jpeg" if path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
    with open(file_path, "rb") as f:
        img_bytes = f.read()
    return extract_via_vlm(img_bytes, mime_type=mime)

def _parse_pdf_vlm_fallback(file_path: str) -> pd.DataFrame:
    from src.agentic_poc.utils.vlm_extractor import extract_via_vlm
    with pdfplumber.open(file_path) as pdf:
        if len(pdf.pages) == 0:
            raise DocumentParsingError("PDF is empty.")
        first_page = pdf.pages[0]
        img = first_page.to_image(resolution=150)
        buf = io.BytesIO()
        img.original.save(buf, format="JPEG")
        img_bytes = buf.getvalue()
        
    return extract_via_vlm(img_bytes, mime_type="image/jpeg")

def parse_document_to_dataframe(file_path: str, max_pages: int = 10, max_size_mb: int = 10, domain: str = None) -> pd.DataFrame:
    """
    Parse a document (PDF or Image) into a pd.DataFrame.
    For PDF: attempts text-based table extraction via pdfplumber. If it fails, falls back to VLM.
    For Image: routes directly to VLM.
    """
    path = pathlib.Path(file_path)
    
    if not path.exists():
        raise DocumentParsingError("File not found.")
        
    if os.path.getsize(path) > max_size_mb * 1024 * 1024:
        raise DocumentParsingError(f"File size exceeds {max_size_mb}MB limit.")
        
    # Is it an image?
    if path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
        if domain not in ["treasury", "expense"]:
            raise DocumentParsingError(f"Image uploads are strictly limited to treasury/expense domains (MVP 1.0). Got: {domain}")
        try:
            return _parse_image_vlm(file_path)
        except Exception as e:
            raise DocumentParsingError(f"VLM Image Parsing Failed: {str(e)}")

    # Otherwise treat as PDF
    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) > max_pages:
                raise DocumentParsingError(f"PDF page limit exceeded ({max_pages}).")
                
            all_rows = []
            headers = None
            
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                    
                for table in tables:
                    if not table:
                        continue
                    if headers is None and len(table) > 1:
                        headers = table[0]
                        all_rows.extend(table[1:])
                    else:
                        all_rows.extend(table)
                        
            if not all_rows:
                # Fallback to VLM for zero tables found
                raise ValueError("No tables found, fallback to VLM.")
                
            if headers:
                clean_headers = [h if h else f"col_{i}" for i, h in enumerate(headers)]
                clean_rows = [row[:len(clean_headers)] + [None] * (len(clean_headers) - len(row)) for row in all_rows]
                df = pd.DataFrame(clean_rows, columns=clean_headers)
            else:
                df = pd.DataFrame(all_rows)
                
            df.attrs["parser_type"] = "pdf_text"
            return df
            
    except (ValueError, Exception) as base_e:
        if domain not in ["treasury", "expense"]:
            raise DocumentParsingError(f"Failed via Text ({str(base_e)}). VLM Fallback is strictly limited to treasury/expense domains (MVP 1.0).")
        # Fallback to Rasterization + VLM
        try:
            df_vlm = _parse_pdf_vlm_fallback(file_path)
            return df_vlm
        except Exception as vlm_e:
            raise DocumentParsingError(f"Failed via Text ({str(base_e)}) AND VLM ({str(vlm_e)})")
