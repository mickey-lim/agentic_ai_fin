from typing import Dict, Any
import pandas as pd
import pathlib
from .core import BaseAdapter, robust_to_numeric

class PayrollAdapter(BaseAdapter):
    @property
    def adapter_id(self) -> str:
        return "ADPTR-PAYROLL-03"

    def collect(self) -> pd.DataFrame:
        target = pathlib.Path("tests/fixtures/payroll_raw.xlsx")
        if target.exists():
            return pd.read_excel(target)
        return pd.DataFrame({"사원번호": [], "이름": [], "기본급": [], "식대(비과세)": [], "4대보험공제": [], "소득세": []})

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        numeric_cols = ['기본급', '식대(비과세)', '4대보험공제', '소득세']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = robust_to_numeric(df[col])
        if '기본급' in df.columns and '식대(비과세)' in df.columns:
            df['지급총액'] = df['기본급'] + df['식대(비과세)']
        if '4대보험공제' in df.columns and '소득세' in df.columns:
            df['공제총액'] = df['4대보험공제'] + df['소득세']
            
        if '지급총액' in df.columns and '공제총액' in df.columns:
            df['실수령액'] = df['지급총액'] - df['공제총액']
        return df

    def draft(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_base = int(df['기본급'].sum()) if '기본급' in df.columns else 0
        total_net = int(df['실수령액'].sum()) if '실수령액' in df.columns else 0
        avg_net = int(df['실수령액'].mean()) if '실수령액' in df.columns and len(df) > 0 else 0
            
        return {
            "total_headcount": len(df),
            "total_base_salary": total_base,
            "total_net_payout": total_net,
            "average_net_payout": avg_net
        }

    def package(self, template_args: Dict[str, Any]) -> str:
        md = f"# 월 급여대장 (Payroll Ledger) 요약\n\n"
        md += f"**총 인원**: {template_args.get('total_headcount', 0)}명\n"
        md += f"**총 기본급**: {template_args.get('total_base_salary', 0):,} 원\n"
        md += f"**당월 실수령액 합계**: {template_args.get('total_net_payout', 0):,} 원\n"
        md += f"**인당 평균 실수령액**: {template_args.get('average_net_payout', 0):,} 원\n"
        md += "\n> 결재 후 즉시 은행 이체 및 명세서 일괄 발송이 예약됩니다.\n"
        return md
