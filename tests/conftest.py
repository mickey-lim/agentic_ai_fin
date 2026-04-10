import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Provide mock JWT_SECRET purely for test initialization boundary
if "JWT_SECRET" not in os.environ:
    os.environ["JWT_SECRET"] = "dummy-testing-secret-with-minimum-32-chars-for-pytest"

import pytest
from src.agentic_poc.graph import build_graph

@pytest.fixture
def workflow_graph():
    return build_graph()
