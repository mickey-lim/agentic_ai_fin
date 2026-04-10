from typing import Dict, Any
import pandas as pd
import pathlib
from .core import BaseAdapter, robust_to_numeric

class TreasuryAdapter(BaseAdapter):
    @property
    def adapter_id(self) -> str:
        return "ADPTR-TREASURY-01"

    def collect(self) -> pd.DataFrame:
        target = pathlib.Path("tests/fixtures/treasury_raw.xlsx")
        if target.exists():
            return pd.read_excel(target)
        return pd.DataFrame({"거래일자": [], "계정과목": [], "공급가액": [], "부가세": [], "승인자": []})

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # Ensure correct column types
        if '공급가액' in df.columns:
            df['공급가액'] = robust_to_numeric(df['공급가액'])
        if '부가세' in df.columns:
            df['부가세'] = robust_to_numeric(df['부가세'])
        return df

    def draft(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_supply = int(df['공급가액'].sum()) if '공급가액' in df.columns else 0
        total_vat = int(df['부가세'].sum()) if '부가세' in df.columns else 0
        total_transactions = len(df)
        
        # Breakdown by account
        breakdown = {}
        if '계정과목' in df.columns:
            breakdown = df.groupby('계정과목')['공급가액'].sum().to_dict()
            
        return {
            "total_supply": total_supply,
            "total_vat": total_vat,
            "total_transactions": total_transactions,
            "account_breakdown": breakdown
        }

    def package(self, template_args: Dict[str, Any]) -> str:
        md = f"# 자금일정/지출결의 요약 리포트\n\n"
        md += f"**총 건수**: {template_args.get('total_transactions', 0)}건\n"
        md += f"**총 공급가액**: {template_args.get('total_supply', 0):,} 원\n"
        md += f"**총 부가세**: {template_args.get('total_vat', 0):,} 원\n"
        md += f"\n## 계정과목별 집행현황\n"
        for account, amt in template_args.get('account_breakdown', {}).items():
            md += f"- **{account}**: {amt:,} 원\n"
        md += "\n> 본 문서는 AI 에이전트(Treasury_Adapter)에 의해 자동 생성되었습니다.\n"
        return md
