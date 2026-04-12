import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Provide mock JWT_SECRET purely for test initialization boundary
if "JWT_SECRET" not in os.environ:
    os.environ["JWT_SECRET"] = "dummy-testing-secret-with-minimum-32-chars-for-pytest"
if "CELERY_TASK_ALWAYS_EAGER" not in os.environ:
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

import pytest
from src.agentic_poc.graph import build_graph

@pytest.fixture
def workflow_graph():
    return build_graph()
