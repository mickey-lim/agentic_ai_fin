import sys
from src.agentic_poc.utils.document_parser import parse_document_to_dataframe

try:
    df = parse_document_to_dataframe("tests/fixtures/real_invoice.pdf", domain="treasury")
    print(df)
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
