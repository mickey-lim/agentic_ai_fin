import logging
import json
import sys
from datetime import datetime, timezone
from src.agentic_poc.config import settings

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Extract custom fields from extra
        for key in ["trace_id", "thread_id", "workflow_id", "owner_id", "component", "event", "status"]:
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)
                
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj, ensure_ascii=False)

class PrettyFormatter(logging.Formatter):
    def format(self, record):
        time_str = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level_str = f"[{record.levelname}]".ljust(10)
        
        base_msg = f"{time_str} {level_str} {record.getMessage()}"
        
        extras = []
        for key in ["trace_id", "thread_id", "workflow_id", "owner_id", "component", "event", "status"]:
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    extras.append(f"{key}={val}")
                    
        if extras:
            base_msg += f" | {' '.join(extras)}"
            
        if record.exc_info:
            base_msg += f"\n{self.formatException(record.exc_info)}"
            
        return base_msg

def get_logger(name: str) -> logging.Logger:
    """
    Factory to retrieve an environment-aware structured logger.
    If settings.APP_ENV == 'prod', outputs structured JSON logs for Datadog/ELK parsing.
    Otherwise, outputs human-readable console string logs.
    """
    logger = logging.getLogger(name)
    
    # Only configure if no handlers are set prevent duplication
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        
        if settings.APP_ENV == "prod":
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(PrettyFormatter())
            
        logger.addHandler(handler)
        logger.propagate = False
        
    return logger
