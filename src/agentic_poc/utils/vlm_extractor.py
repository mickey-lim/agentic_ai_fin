import base64
import os
import pathlib
import io
from typing import List, Dict, Any, Optional
import pandas as pd
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

class ReceiptRow(BaseModel):
    date: Optional[str] = Field(None, description="Date of the transaction or item")
    description: Optional[str] = Field(None, description="Item description, name, or content")
    quantity: Optional[int] = Field(None, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Unit price")
    amount: Optional[int] = Field(None, description="Total amount / price")
    category: Optional[str] = Field(None, description="Category of expenses")

class ReceiptParsingResult(BaseModel):
    items: List[ReceiptRow] = Field(default_factory=list, description="Extracted line items from the document")
    total_amount: Optional[int] = Field(None, description="Total summary amount")
    vendor: Optional[str] = Field(None, description="Vendor or company name")
    confidence: str = Field(..., description="High, Medium, or Low based on clarity")

def extract_via_vlm(image_bytes: bytes, mime_type: str = "image/jpeg") -> pd.DataFrame:
    """
    Given image bytes, extracts receipt tabular data using Gemini Vision.
    Strictly enforced low temperature and structured output schema.
    """
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.0)
    structured_llm = llm.with_structured_output(ReceiptParsingResult)
    
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    
    msg = HumanMessage(
        content=[
            {
                "type": "text", 
                "text": "You are a precise OCR data extraction AI. Extract all tabular items, line items, and quantities from this receipt or financial document. Ensure values are accurate. Output empty strings if something is missing. Include the total amount and vendor."
            },
            {
                "type": "image_url", 
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"}
            }
        ]
    )
    
    # We call standard structured output
    result: ReceiptParsingResult = structured_llm.invoke([msg])
    
    # Check low confidence
    if result.confidence.lower() == "low" and not result.items:
        raise ValueError("VLM returned low confidence and no items were extracted.")
        
    df_data = []
    for item in result.items:
        df_data.append({
            "일자": item.date,
            "내용": item.description,
            "수량": item.quantity,
            "단가": item.unit_price,
            "금액": item.amount,
            "구분": item.category,
            "_vendor": result.vendor,
            "_total_inferred": result.total_amount,
            "_vlm_confidence": result.confidence
        })
        
    if not df_data:
        # If no items but somehow didn't raise, push generic summary
        df_data.append({
            "일자": None,
            "내용": f"{result.vendor} 영수증",
            "수량": 1,
            "단가": result.total_amount,
            "금액": result.total_amount,
            "구분": "VLM_INFERRED",
            "_vendor": result.vendor,
            "_total_inferred": result.total_amount,
            "_vlm_confidence": result.confidence
        })
        
    df = pd.DataFrame(df_data)
    df.attrs["parser_type"] = "vlm_receipt"
    df.attrs["confidence"] = result.confidence
    return df
