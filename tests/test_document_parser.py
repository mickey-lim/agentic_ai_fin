import pytest
import pandas as pd
from src.agentic_poc.utils.document_parser import parse_document_to_dataframe, DocumentParsingError
from unittest.mock import MagicMock, patch

class MockPage:
    def __init__(self, tables):
        self.tables = tables

    def extract_tables(self):
        return self.tables

class MockPDF:
    def __init__(self, pages):
        self.pages = [MockPage(p) for p in pages]

    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

@patch('src.agentic_poc.utils.document_parser.os.path.getsize')
@patch('src.agentic_poc.utils.document_parser.pathlib.Path.exists')
@patch('src.agentic_poc.utils.document_parser.pdfplumber.open')
def test_parse_pdf_success(mock_open, mock_exists, mock_getsize):
    mock_exists.return_value = True
    mock_getsize.return_value = 1024 * 1024 # 1MB
    
    # Mock a PDF with one page, one table
    mock_open.return_value = MockPDF([
        [[["Header1", "Header2"], ["Val1", "Val2"]]]
    ])
    
    df = parse_document_to_dataframe("dummy.pdf", domain="treasury")
    
    assert list(df.columns) == ["Header1", "Header2"]
    assert len(df) == 1
    assert df.iloc[0]["Header1"] == "Val1"
    assert df.attrs.get("parser_type") == "pdf_text"

@patch('src.agentic_poc.utils.document_parser.os.path.getsize')
@patch('src.agentic_poc.utils.document_parser.pathlib.Path.exists')
@patch('src.agentic_poc.utils.document_parser.pdfplumber.open')
def test_parse_pdf_unsupported_layout(mock_open, mock_exists, mock_getsize):
    mock_exists.return_value = True
    mock_getsize.return_value = 1000 
    
    # PDF with NO tables
    mock_open.return_value = MockPDF([[]])
    
    with pytest.raises(DocumentParsingError, match="Fallback is strictly limited to"):
        parse_document_to_dataframe("dummy2.pdf", domain="other")

@patch('src.agentic_poc.utils.document_parser.os.path.getsize')
@patch('src.agentic_poc.utils.document_parser.pathlib.Path.exists')
def test_parse_pdf_file_size_exceeded(mock_exists, mock_getsize):
    mock_exists.return_value = True
    mock_getsize.return_value = 11 * 1024 * 1024 # 11MB
    
    with pytest.raises(DocumentParsingError, match="limit"):
        parse_document_to_dataframe("dummy3.pdf", max_size_mb=10, domain="treasury")
