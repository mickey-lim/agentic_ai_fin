import pathlib
import zipfile
import datetime
import pandas as pd
import json
import time
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from ..schemas import Status, AIType
from ..state import AgentState
from ..adapters import get_adapter

def worker_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    할당된 Task를 수행하고 결과물(Artifacts)을 생성하는 메인 워커 노드입니다.
    - 주요 변경(v5): 내부 태스크(normalize, draft 등)가 외부 데이터를 중복 수집하지 않고,
      이전 단계(t['depends_on'])에서 확정된 Snapshot 엑셀을 로드하도록 불변 파이프라인을 지원합니다.
    """
    start_time = time.perf_counter()
    run_id = config.get("configurable", {}).get("run_id") if config else None
    if not run_id:
        run_id = config.get("run_id") if config else None
        
    tasks = state.get("tasks", [])
    results = state.get("results", [])
    error_count = state.get("error_count", 0)
    process_family = state.get("process_family", "unknown")
    workflow_id = state.get("workflow_id", "unknown_wf")
    
    # Init Adapter
    adapter = get_adapter(process_family)
    
    telemetry_logs = []
    completed_task_ids = {r["task_id"] for r in results}
    new_results = []
    
    for t in tasks:
        if t["task_id"] not in completed_task_ids:
            current_states = {r["task_id"]: r["status"] for r in (results + new_results)}
            deps_met = True
            for d in t.get("depends_on", []):
                dep_status = current_states.get(d)
                if t["task_type"] == "package" and dep_status == Status.PARTIAL.value:
                    pass 
                elif dep_status != Status.SUCCESS.value:
                    deps_met = False
                    break
            
            if deps_met:
                status = Status.SUCCESS.value
                output_data = {"processed": True}
                evidence_list = []
                
                try:
                    target_file = pathlib.Path(f"./artifacts/evidence/{t['task_id']}_{workflow_id}_raw.xlsx")
                    if t["task_type"] == "collect":
                        evidence_dir = pathlib.Path("./artifacts/evidence")
                        evidence_dir.mkdir(parents=True, exist_ok=True)
                        
                        source_file_id = state.get("source_file_id")
                        df = adapter.collect(source_file_id)
                        df.to_excel(target_file, index=False)
                        
                        output_data["collected_path"] = str(target_file)
                        evidence_list.append(str(target_file))
                        parser_type = getattr(df, "attrs", {}).get("parser_type", "excel/csv")
                        
                        # Preserve existing provenance, update with sequence logic
                        current_prov = dict(state.get("provenance", {}))
                        current_prov.update({
                            "adapter": adapter.adapter_id, 
                            "operation": "collect",
                            "parser_type": parser_type
                        })
                        output_data["provenance"] = current_prov
                        
                    elif t["task_type"] == "normalize":
                        # Needs previous collect to run
                        collect_task_id = next((d for d in t.get("depends_on", []) if d.startswith("collect")), None)
                        if not collect_task_id:
                            raise ValueError("Normalize task missing collect dependency")
                            
                        collect_target = pathlib.Path(f"./artifacts/evidence/{collect_task_id}_{workflow_id}_raw.xlsx")
                        df = pd.read_excel(collect_target)
                        df = adapter.normalize(df)
                        norm_target = pathlib.Path(f"./artifacts/evidence/{t['task_id']}_{workflow_id}_norm.xlsx")
                        df.to_excel(norm_target, index=False)
                        
                        output_data["normalized_path"] = str(norm_target)
                        evidence_list.append(str(norm_target))
                        current_prov = dict(state.get("provenance", {}))
                        current_prov.update({"adapter": adapter.adapter_id, "operation": "normalize"})
                        output_data["provenance"] = current_prov

                    elif t["task_type"] == "draft":
                        if "force_fail" in state.get("input_request", ""):
                            status = Status.FAILED.value
                            error_count += 1
                            if error_count < 3:
                                latency_ms = int((time.perf_counter() - start_time) * 1000)
                                telemetry_logs.append({
                                    "node": "worker",
                                    "timestamp": datetime.datetime.now().isoformat(),
                                    "event": f"TASK_EXEC:{t['task_id']}",
                                    "status": "error",
                                    "latency_ms": latency_ms,
                                    "importance": "primary",
                                    "error_summary": f"Simulated force_fail. Attempt {error_count}",
                                    "langsmith_run_id": str(run_id)
                                })
                                return {"error_count": error_count, "telemetry_logs": telemetry_logs}
                        else:
                            norm_task_id = next((d for d in t.get("depends_on", []) if d.startswith("normalize")), None)
                            if not norm_task_id:
                                raise ValueError("Draft task missing normalize dependency")
                                
                            norm_target = pathlib.Path(f"./artifacts/evidence/{norm_task_id}_{workflow_id}_norm.xlsx")
                            df = pd.read_excel(norm_target)
                            draft_res = adapter.draft(df)
                            
                            draft_target = pathlib.Path(f"./artifacts/evidence/{t['task_id']}_{workflow_id}_draft.json")
                            with open(draft_target, "w") as f:
                                json.dump(draft_res, f, ensure_ascii=False, indent=2)
                                
                            output_data["draft_summary"] = draft_res
                            evidence_list.append(str(draft_target))
                            current_prov = dict(state.get("provenance", {}))
                            current_prov.update({"adapter": adapter.adapter_id, "operation": "draft"})
                            output_data["provenance"] = current_prov

                        if t["ai_type"] == AIType.AI_ASSISTED.value and status != Status.FAILED.value:
                            status = Status.PARTIAL.value
                            output_data["draft_ready"] = True
                        if t["ai_type"] == AIType.HUMAN_ONLY.value and status != Status.FAILED.value:
                            status = Status.PARTIAL.value
                            output_data["external_handoff_ready"] = True
                            
                    elif t["task_type"] == "package":
                        evidence_dir = pathlib.Path("./artifacts/evidence")
                        package_dir = pathlib.Path("./artifacts/package")
                        package_dir.mkdir(parents=True, exist_ok=True)
                        
                        package_file = package_dir / f"final_pkg_{workflow_id}.zip"
                        report_file = evidence_dir / f"report_{workflow_id}.md"
                        
                        # Gather all draft data if exists
                        draft_json = evidence_dir.glob(f"*_{workflow_id}_draft.json")
                        template_args = {}
                        for j in draft_json:
                            with open(j, "r") as f:
                                template_args.update(json.load(f))
                        
                        md_str = adapter.package(template_args)
                        with open(report_file, "w") as f:
                            f.write(md_str)
                            
                        with zipfile.ZipFile(package_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for item in evidence_dir.glob(f"*_{workflow_id}*.*"):
                                zipf.write(item, item.name)
                                
                        output_data["handoff_package_ready"] = True
                        output_data["package_path"] = str(package_file)
                        output_data["report_path"] = str(report_file)
                        evidence_list.append(str(package_file))
                        evidence_list.append(str(report_file))
                        current_prov = dict(state.get("provenance", {}))
                        current_prov.update({"adapter": adapter.adapter_id, "operation": "package"})
                        output_data["provenance"] = current_prov

                except Exception as e:
                    status = Status.FAILED.value
                    output_data["error"] = str(e)
                    error_count += 1
                
                res = {
                    "task_id": t["task_id"],
                    "status": status,
                    "output": output_data,
                    "evidence": evidence_list,
                    "cost": {"tokens_in": 10, "tokens_out": 5},
                    "latency_ms": int((time.perf_counter() - start_time) * 1000)
                }
                new_results.append(res)
                
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                telemetry_logs.append({
                    "node": "worker",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "event": f"TASK_EXEC:{t['task_id']}",
                    "status": "success" if status == Status.SUCCESS.value else ("partial" if status == Status.PARTIAL.value else "error"),
                    "latency_ms": latency_ms,
                    "importance": "primary",
                    "langsmith_run_id": str(run_id),
                    "error_summary": output_data.get("error") if status == Status.FAILED.value else None
                })
                break
                
    if not new_results:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        telemetry_logs.append({
            "node": "worker",
            "timestamp": datetime.datetime.now().isoformat(),
            "event": "NO_OP",
            "status": "success",
            "latency_ms": latency_ms,
            "importance": "primary",
            "langsmith_run_id": str(run_id)
        })

    return {
        "results": new_results,
        "error_count": error_count,
        "telemetry_logs": telemetry_logs
    }
