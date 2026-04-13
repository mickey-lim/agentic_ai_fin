import pytest
from unittest.mock import patch
from src.agentic_poc.utils.vlm_extractor import extract_via_vlm, ReceiptParsingResult

@patch("src.agentic_poc.utils.vlm_extractor.ChatGoogleGenerativeAI")
def test_vlm_extractor_raises_value_error_on_empty_items(mock_chat_cls):
    """
    Test the critical fail-closed logic where the VLM fails to extract any valid line items.
    The system should NEVER just swallow the result and create a spurious 'VLM_INFERRED' item without real data.
    """
    # Create the mock instance that will be returned when ChatGoogleGenerativeAI() is called
    mock_llm_instance = mock_chat_cls.return_value
    
    # Create the mock structured LLM that with_structured_output() will return
    mock_structured_llm = mock_llm_instance.with_structured_output.return_value
    
    # Mock the returned result from invoke()
    mock_result = ReceiptParsingResult(
        items=[], 
        total_amount=0, 
        vendor="UNKNOWN", 
        confidence="LOW"
    )
    mock_structured_llm.invoke.return_value = mock_result
    
    fake_image_bytes = b"fakeimage"
    
    with pytest.raises(ValueError, match="VLM returned no valid line items"):
        extract_via_vlm(fake_image_bytes)
