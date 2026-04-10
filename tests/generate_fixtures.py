import pandas as pd
import pathlib

fixture_dir = pathlib.Path("tests/fixtures")
fixture_dir.mkdir(parents=True, exist_ok=True)

# 1. Treasury / Expense (자금보고)
treasury_df = pd.DataFrame({
    "거래일자": ["2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27"],
    "계정과목": ["여비교통비", "소모품비", "지급수수료", "임차료"],
    "공급가액": [150000, 300000, 50000, 1500000],
    "부가세": [15000, 30000, 5000, 150000],
    "승인자": ["홍길동", "홍길동", "이순신", "이순신"]
})
treasury_df.to_excel(fixture_dir / "treasury_raw.xlsx", index=False)

# 2. Withholding (원천세)
withholding_df = pd.DataFrame({
    "귀속월": ["2026-03", "2026-03", "2026-03"],
    "종류": ["근로소득", "사업소득(3.3%)", "기타소득"],
    "인원수": [10, 5, 2],
    "총지급액": [50000000, 15000000, 5000000],
    "원천징수세액": [500000, 495000, 250000]
})
withholding_df.to_excel(fixture_dir / "withholding_raw.xlsx", index=False)

# 3. Payroll (급여)
payroll_df = pd.DataFrame({
    "사원번호": ["EMP-001", "EMP-002", "EMP-003", "EMP-004"],
    "이름": ["김철수", "이영희", "박지민", "최동훈"],
    "기본급": [4000000, 3500000, 5000000, 3000000],
    "식대(비과세)": [100000, 100000, 100000, 100000],
    "4대보험공제": [350000, 300000, 450000, 250000],
    "소득세": [150000, 120000, 300000, 80000]
})
payroll_df.to_excel(fixture_dir / "payroll_raw.xlsx", index=False)

# 4. Grant (보조금/지원금)
grant_df = pd.DataFrame({
    "집행일자": ["2026-03-10", "2026-03-15", "2026-03-20"],
    "비목": ["인건비", "재료비", "운영비"],
    "세목": ["참여연구원", "소프트웨어 구매", "회의비"],
    "승인금액": [10000000, 5000000, 2000000],
    "집행금액": [8000000, 5000000, 1500000]
})
grant_df.to_excel(fixture_dir / "grant_raw.xlsx", index=False)

print("Fixtures generated successfully!")
