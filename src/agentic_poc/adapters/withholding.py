from typing import Dict, Any
import pandas as pd
import pathlib
from .core import BaseAdapter, robust_to_numeric

class WithholdingAdapter(BaseAdapter):
    @property
    def adapter_id(self) -> str:
        return "ADPTR-WITHHOLDING-02"

    def collect(self) -> pd.DataFrame:
        target = pathlib.Path("tests/fixtures/withholding_raw.xlsx")
        if target.exists():
            return pd.read_excel(target)
        return pd.DataFrame({"귀속월": [], "종류": [], "인원수": [], "총지급액": [], "원천징수세액": []})

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if '총지급액' in df.columns:
            df['총지급액'] = robust_to_numeric(df['총지급액'])
        if '원천징수세액' in df.columns:
            df['원천징수세액'] = robust_to_numeric(df['원천징수세액'])
        return df

    def draft(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_payout = int(df['총지급액'].sum()) if '총지급액' in df.columns else 0
        total_tax = int(df['원천징수세액'].sum()) if '원천징수세액' in df.columns else 0
        total_headcount = int(df['인원수'].sum()) if '인원수' in df.columns else 0
        
        breakdown = {}
        if '종류' in df.columns:
            breakdown = df.groupby('종류')['원천징수세액'].sum().to_dict()
            
        return {
            "total_payout": total_payout,
            "total_tax": total_tax,
            "total_headcount": total_headcount,
            "tax_breakdown": breakdown
        }

    def package(self, template_args: Dict[str, Any]) -> str:
        md = f"# 원천징수이행상황신고서 초안\n\n"
        md += f"**신고 인원**: {template_args.get('total_headcount', 0)}명\n"
        md += f"**당월 총 지급액**: {template_args.get('total_payout', 0):,} 원\n"
        md += f"**당월 원천징수 세액**: {template_args.get('total_tax', 0):,} 원\n"
        md += f"\n## 소득 종류별 세액\n"
        for kind, tax in template_args.get('tax_breakdown', {}).items():
            md += f"- **{kind}**: {tax:,} 원\n"
        md += "\n> 본 문서는 Hometax API 전송 이전에 담당자 검토용으로 생성되었습니다.\n"
        return md
