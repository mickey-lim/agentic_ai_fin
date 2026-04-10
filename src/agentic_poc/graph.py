from langgraph.graph import StateGraph, START, END


from .state import AgentState
from .nodes.planner import planner_node
from .nodes.worker import worker_node
from .nodes.dispatcher import dispatcher_node, route_dispatcher
from .nodes.result_compiler import result_compiler_node
from .nodes.human_review import human_review_node



def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    
    workflow.add_node("planner", planner_node)
    workflow.add_node("dispatcher", dispatcher_node)
    workflow.add_node("worker", worker_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("result_compiler", result_compiler_node)
    
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "dispatcher")
    
    workflow.add_conditional_edges(
        "dispatcher",
        route_dispatcher,
        {
            "worker": "worker",
            "human_review": "human_review",
            "result_compiler": "result_compiler"
        }
    )
    
    workflow.add_edge("worker", "dispatcher")
    workflow.add_edge("human_review", "dispatcher")
    workflow.add_edge("result_compiler", END)
    
    return workflow
