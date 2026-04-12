from typing import Optional
from typing import Dict, Any, Optional
import pandas as pd
from abc import ABC, abstractmethod
import sqlite3
import pathlib
from src.agentic_poc.config import settings

def robust_to_numeric(s: pd.Series) -> pd.Series:
    """Safely converts a pandas Series with potentially string-formatted numbers (with commas) or NaNs to int."""
    try:
        s = s.astype(str).str.replace(',', '', regex=False).str.strip()
        s = s.replace(['nan', 'None', ''], pd.NA)
    except Exception:
        pass
    return pd.to_numeric(s, errors='coerce').fillna(0).astype(int)

def normalize_columns(df: pd.DataFrame, expected_columns: list[str], domain_synonyms: dict = None) -> pd.DataFrame:
    """
    Renames inferred/synonym columns to the strictly expected schema required by the domains.
    e.g. '금액', '합계' -> '공급가액'
    """
    if domain_synonyms is None:
        domain_synonyms = {}
        
    # Reverse mapping for quick lookup
    # Only map if the target expected column is missing and synonym exists
    df_cols = list(df.columns)
    rename_map = {}
    
    for expected in expected_columns:
        if expected in df_cols:
            continue # Already correct
            
        candidate_synonyms = domain_synonyms.get(expected, [])
        for syn in candidate_synonyms:
            # Check if any synonym exists in current cols
            # Use lower/strip for robustness
            match = next((col for col in df_cols if str(col).replace(" ", "").lower() == syn.replace(" ", "").lower()), None)
            if match and match not in rename_map.keys():
                rename_map[match] = expected
                break
                
    if rename_map:
        df = df.rename(columns=rename_map)
        
    return df

class BaseAdapter(ABC):
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Globally unique adapter identifier."""
        pass

    def resolve_source_path(self, source_file_id: Optional[str]) -> Optional[str]:
        """Resolves an opaque file_id to a verified local path using the synchronous SQLite driver."""
        if not source_file_id:
            return None
            
        try:
            with sqlite3.connect(settings.REGISTRY_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT stored_path FROM file_registry WHERE file_id = ?", (source_file_id,))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception:
            pass
        return None

    @abstractmethod
    def collect(self, source_file_id: Optional[str] = None) -> pd.DataFrame:
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
