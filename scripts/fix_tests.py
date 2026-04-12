import re

def fix():
    with open("tests/test_e2e_upload_workflow.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Rename pdf_parser to document_parser
    content = content.replace("src.agentic_poc.utils.pdf_parser", "src.agentic_poc.utils.document_parser")
    content = content.replace("pdf_parser.parse_pdf_to_dataframe", "document_parser.parse_document_to_dataframe")

    # Change "source_file_id": file_id to "source_file_ids": [file_id]
    content = re.sub(
        r'"source_file_id":\s*(\w+)',
        r'"source_file_ids": [\1]',
        content
    )

    with open("tests/test_e2e_upload_workflow.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix()
