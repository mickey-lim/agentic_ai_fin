import re
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class PIIRedactionMiddleware:
    """
    경량화된 PII Redaction 미들웨어 컨셉 모듈.
    추후 Microsoft Presidio 등 엔터프라이즈급 모듈로 교체될 수 있도록 인터페이스를 단순화.
    """
    def __init__(self):
        # 정규식 패턴 (주민/계좌/카드/이메일/번호)
        self.patterns = {
            "RRN": re.compile(r'\b\d{6}[-\s]*[1-4]\d{6}\b'),
            "CARD_NUMBER": re.compile(r'\b(?:\d[ -]*?){13,16}\b'),
            "BANK_ACCOUNT": re.compile(r'\b\d{3,6}[-\s]*\d{2,6}[-\s]*\d{4,9}\b'),
            "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'),
            "PHONE": re.compile(r'\b01[016789][-\s]*\d{3,4}[-\s]*\d{4}\b')
        }

    def _redact_text(self, text: str) -> Tuple[str, Dict[str, int]]:
        redacted_text = text
        counts = {k: 0 for k in self.patterns.keys()}
        
        for pii_type, pattern in self.patterns.items():
            matches = pattern.findall(redacted_text)
            if matches:
                counts[pii_type] += len(matches)
                redacted_text = pattern.sub(f"[REDACTED_{pii_type}]", redacted_text)
                
        return redacted_text, counts

    def invoke(self, text: str) -> str:
        if not text:
            return text
            
        redacted_text, counts = self._redact_text(text)
        
        # Redaction 로깅 (감사 용도)
        total_redacted = sum(counts.values())
        if total_redacted > 0:
            logger.warning(f"[PII REDACTION] {total_redacted} fields redacted before LLM routing: {counts}")
            
        return redacted_text

pii_middleware = PIIRedactionMiddleware()
