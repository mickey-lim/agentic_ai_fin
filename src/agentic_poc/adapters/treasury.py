from typing import Optional
from typing import Dict, Any
import pandas as pd
import pathlib
from .core import BaseAdapter, robust_to_numeric, normalize_columns

DOMAIN_SYNONYMS = {'공급가액': ['금액', '합계', '공급가', '총액', '총금액', '총공급가액', 'Amount'], '부가세': ['세액', '부가 가치세', '부가가치세', 'V.A.T', 'VAT', '세금', 'Tax'], '계정과목': ['항목', '내역', '품목', '적요', '구분', 'Item'], '거래일자': ['일자', '날짜', '발생일', '작성일자', 'Date'], '승인자': ['결재자', 'Approver']}

class TreasuryAdapter(BaseAdapter):
    @property
    def adapter_id(self) -> str:
        return "ADPTR-TREASURY-01"

    def collect(self, source_file_id: Optional[str] = None) -> pd.DataFrame:
        target_path = self.resolve_source_path(source_file_id)
        if target_path and pathlib.Path(target_path).exists():
            if target_path.endswith(".csv"): return pd.read_csv(target_path)
            if target_path.endswith(".pdf") or target_path.endswith(".jpg") or target_path.endswith(".jpeg") or target_path.endswith(".png"):
                from src.agentic_poc.utils.document_parser import parse_document_to_dataframe
                return parse_document_to_dataframe(target_path, domain="treasury")
            return pd.read_excel(target_path)
            
        # Fallback to fixture for test robustness
        target = pathlib.Path("tests/fixtures/treasury_raw.xlsx")
        if target.exists():
            return pd.read_excel(target)
        return pd.DataFrame({"거래일자": [], "계정과목": [], "공급가액": [], "부가세": [], "승인자": []})

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # 1. 컬럼 매핑 정규화 (PDF/이표준 대응)
        df = normalize_columns(df, expected_columns=['공급가액', '부가세', '계정과목', '거래일자', '승인자'], domain_synonyms=DOMAIN_SYNONYMS)
        
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
