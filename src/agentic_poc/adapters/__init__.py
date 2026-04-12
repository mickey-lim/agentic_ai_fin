from typing import Optional
from .core import BaseAdapter
from .treasury import TreasuryAdapter
from .withholding import WithholdingAdapter
from .payroll import PayrollAdapter
from .grant import GrantAdapter

def get_adapter(process_family: str) -> BaseAdapter:
    """Factory method to get the correct adapter based on the ProcessFamily string."""
    pf = str(process_family).lower()
    if pf == "treasury":
        return TreasuryAdapter()
    elif pf == "withholding":
        return WithholdingAdapter()
    elif pf == "payroll":
        return PayrollAdapter()
    elif pf == "grant":
        return GrantAdapter()
    
    # Defaults to Treasury if unknown, to avoid crashing the PoC.
    return TreasuryAdapter()
