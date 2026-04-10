import pytest
import pandas as pd
import numpy as np
from src.agentic_poc.adapters.treasury import TreasuryAdapter
from src.agentic_poc.adapters.withholding import WithholdingAdapter
from src.agentic_poc.adapters.payroll import PayrollAdapter
from src.agentic_poc.adapters.grant import GrantAdapter

def test_treasury_adapter_edge_cases():
    adapter = TreasuryAdapter()
    
    # Edge case 1: string formatted with commas, NaNs, mixed types
    df_raw = pd.DataFrame({
        "거래일자": ["2026-03-24", "2026-03-25", None],
        "계정과목": ["기타", "소모품비", np.nan],
        "공급가액": ["1,000", "2,500.5", np.nan], 
        "부가세": ["100", 250, None],
        "승인자": ["홍길동", None, "김철수"]
    })
    
    df_norm = adapter.normalize(df_raw)
    
    # Assert missing filled with 0s and strings properly cast
    assert df_norm.iloc[0]["공급가액"] == 1000
    assert df_norm.iloc[1]["공급가액"] == 2500
    assert df_norm.iloc[2]["공급가액"] == 0
    assert df_norm.iloc[1]["부가세"] == 250
    assert df_norm.iloc[2]["부가세"] == 0
    
    draft_res = adapter.draft(df_norm)
    assert draft_res["total_supply"] == 3500
    assert draft_res["total_vat"] == 350
    assert draft_res["total_transactions"] == 3
    assert draft_res["account_breakdown"]["기본값0이아닌것"] if 0 in draft_res["account_breakdown"] else True

def test_empty_dataframe_resilience():
    # If a completely empty dataframe or unmatching columns comes in, it shouldn't crash
    df_empty = pd.DataFrame()
    
    adapters = [TreasuryAdapter(), WithholdingAdapter(), PayrollAdapter(), GrantAdapter()]
    
    for adapter in adapters:
        df_norm = adapter.normalize(df_empty)
        draft_res = adapter.draft(df_norm)
        # Should not raise exception
        assert isinstance(draft_res, dict)

def test_physical_collect_integrity():
    """
    Smoke test to ensure the actual paths the adapters use for .xlsx I/O are intact 
    and parsable locally. This defends against 'file not found' issues in deployed environments.
    """
    adapters = [TreasuryAdapter(), WithholdingAdapter(), PayrollAdapter(), GrantAdapter()]
    for adapter in adapters:
        # Collect loads the Excel file
        df = adapter.collect()
        # Should return a DataFrame
        assert isinstance(df, pd.DataFrame)
        # Should have data
        assert len(df) > 0, f"Adapter {adapter.adapter_id} failed to read physical fixture or data is empty."
        
def test_withholding_adapter_edge_cases():
    adapter = WithholdingAdapter()
    df_raw = pd.DataFrame({
        "총지급액": ["10,000,000", "2,000,000 ", ""],
        "원천징수세액": ["330,000", np.nan, "100"]
    })
    df_norm = adapter.normalize(df_raw)
    assert df_norm["총지급액"].tolist() == [10000000, 2000000, 0]
    assert df_norm["원천징수세액"].tolist() == [330000, 0, 100]

def test_payroll_adapter_edge_cases():
    adapter = PayrollAdapter()
    df_raw = pd.DataFrame({
        "기본급": ["3,000,000", 2500000],
        "식대(비과세)": ["200,000", np.nan],
        "4대보험공제": ["300,000", "200000"],
        "소득세": ["150,000", 0]
    })
    df_norm = adapter.normalize(df_raw)
    
    assert df_norm["기본급"].tolist() == [3000000, 2500000]
    assert df_norm["식대(비과세)"].tolist() == [200000, 0]
    
    draft_res = adapter.draft(df_norm)
    assert draft_res["total_net_payout"] == (3200000 - 450000) + (2500000 - 200000)

def test_grant_adapter_edge_cases():
    adapter = GrantAdapter()
    df_raw = pd.DataFrame({
        "승인금액": ["50,000,000", "150000"],
        "집행금액": ["10,000,000", "0"]
    })
    df_norm = adapter.normalize(df_raw)
    assert df_norm["잔액"].tolist() == [40000000, 150000]
    draft_res = adapter.draft(df_norm)
    assert draft_res["total_approved"] == 50150000
    assert draft_res["total_executed"] == 10000000
