from typing import Dict, Any, Optional
import pandas as pd
from abc import ABC, abstractmethod

def robust_to_numeric(s: pd.Series) -> pd.Series:
    """Safely converts a pandas Series with potentially string-formatted numbers (with commas) or NaNs to int."""
    try:
        s = s.astype(str).str.replace(',', '', regex=False).str.strip()
        s = s.replace(['nan', 'None', ''], pd.NA)
    except Exception:
        pass
    return pd.to_numeric(s, errors='coerce').fillna(0).astype(int)

class BaseAdapter(ABC):
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Globally unique adapter identifier."""
        pass

    @abstractmethod
    def collect(self) -> pd.DataFrame:
        """In a real system, hits a 3rd party API or local system. Returns raw DataFrame."""
        pass

    @abstractmethod
    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Cleans and standardizes raw data into the canonical schema."""
        pass

    @abstractmethod
    def draft(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates numerical summaries and constructs draft payload JSON."""
        pass
        
    @abstractmethod
    def package(self, template_args: Dict[str, Any]) -> str:
        """Formats the draft summary into Markdown and returns markdown string."""
        pass
