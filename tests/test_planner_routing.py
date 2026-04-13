import pytest
from src.agentic_poc.nodes.planner import planner_node

def test_planner_receipt_routing():
    res = planner_node({"input_request": "영수증 3장을 정리해줘", "process_family_override": None}, None)
    assert res["process_family"] == "expense"
    
def test_planner_지출결의서_routing():
    res = planner_node({"input_request": "지출결의서 영수증 검토", "process_family_override": None}, None)
    assert res["process_family"] == "expense"
    
def test_planner_receipt_english_routing():
    res = planner_node({"input_request": "Process this receipt for me", "process_family_override": None}, None)
    assert res["process_family"] == "expense"

def test_planner_default_vat_routing():
    res = planner_node({"input_request": "알 수 없는 임의의 요청", "process_family_override": None}, None)
    assert res["process_family"] == "vat"
