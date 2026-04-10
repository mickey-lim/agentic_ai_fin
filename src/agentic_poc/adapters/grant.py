from typing import Dict, Any
import pandas as pd
import pathlib
from .core import BaseAdapter, robust_to_numeric

class GrantAdapter(BaseAdapter):
    @property
    def adapter_id(self) -> str:
        return "ADPTR-GRANT-04"

    def collect(self) -> pd.DataFrame:
        target = pathlib.Path("tests/fixtures/grant_raw.xlsx")
        if target.exists():
            return pd.read_excel(target)
        return pd.DataFrame({"집행일자": [], "비목": [], "세목": [], "승인금액": [], "집행금액": []})

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if '승인금액' in df.columns:
            df['승인금액'] = robust_to_numeric(df['승인금액'])
        if '집행금액' in df.columns:
            df['집행금액'] = robust_to_numeric(df['집행금액'])
            
        if '승인금액' in df.columns and '집행금액' in df.columns:
            df['잔액'] = df['승인금액'] - df['집행금액']
        return df

    def draft(self, df: pd.DataFrame) -> Dict[str, Any]:
        total_approved = int(df['승인금액'].sum()) if '승인금액' in df.columns else 0
        total_executed = int(df['집행금액'].sum()) if '집행금액' in df.columns else 0
        total_balance = int(df['잔액'].sum()) if '잔액' in df.columns else 0
        
        burn_rate = (total_executed / total_approved * 100) if total_approved > 0 else 0
            
        return {
            "total_approved": total_approved,
            "total_executed": total_executed,
            "total_balance": total_balance,
            "burn_rate": round(burn_rate, 2),
            "execution_count": len(df)
        }

    def package(self, template_args: Dict[str, Any]) -> str:
        md = f"# 정부보조금/지원금 집행 결산 리포트\n\n"
        md += f"**집행 건수**: {template_args.get('execution_count', 0)}건\n"
        md += f"**총 승인 예산**: {template_args.get('total_approved', 0):,} 원\n"
        md += f"**당기 누적 집행액**: {template_args.get('total_executed', 0):,} 원\n"
        md += f"**예산 잔액**: {template_args.get('total_balance', 0):,} 원\n"
        md += f"**예산 소진율 (Burn Rate)**: {template_args.get('burn_rate', 0)}%\n"
        md += "\n> 본 문서는 e-나라도움/RCMS 업로드 검증용으로 자동 생성되었습니다.\n"
        return md
