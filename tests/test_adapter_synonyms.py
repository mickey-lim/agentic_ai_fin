import pytest
import pandas as pd
from src.agentic_poc.adapters.grant import GrantAdapter
from src.agentic_poc.adapters.payroll import PayrollAdapter
from src.agentic_poc.adapters.withholding import WithholdingAdapter

def test_grant_synonyms():
    df = pd.DataFrame({
        "결제일": ["2026-04-12"],
        "예산비목": ["의료비"],
        "상세내역": ["검진비"],
        "예산금액": [500000],
        "사용금액": [100000]
    })
    
    adapter = GrantAdapter()
    norm_df = adapter.normalize(df)
    
    assert list(norm_df.columns) == ["집행일자", "비목", "세목", "승인금액", "집행금액", "잔액"]

def test_payroll_synonyms():
    df = pd.DataFrame({
        "사번": ["E101"],
        "대상자명": ["Mickey"],
        "본봉": [5000000],
        "중식비": [200000],
        "보험료": [300000],
        "원천세": [150000]
    })
    
    adapter = PayrollAdapter()
    norm_df = adapter.normalize(df)
    
    expected_cols = ["사원번호", "이름", "기본급", "식대(비과세)", "4대보험공제", "소득세", "지급총액", "공제총액", "실수령액"]
    for c in expected_cols:
        assert c in norm_df.columns

def test_withholding_synonyms():
    df = pd.DataFrame({
        "월별": ["2026-04"],
        "소득종류": ["근로소득"],
        "인원": [5],
        "지급총액": [15000000],
        "징수세액": [800000]
    })
    
    adapter = WithholdingAdapter()
    norm_df = adapter.normalize(df)
    
    assert list(norm_df.columns) == ["귀속월", "종류", "인원수", "총지급액", "원천징수세액"]
