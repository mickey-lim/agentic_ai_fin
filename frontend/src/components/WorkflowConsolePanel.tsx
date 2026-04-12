"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, ShieldCheck, FileCheck, CheckCircle2, Clock, AlertCircle, Activity, ChevronDown, ChevronRight } from "lucide-react";

export type TelemetryLog = {
  node: string;
  timestamp: string;
  event: string;
  status: "success" | "error";
  latency_ms: number;
  importance?: "primary" | "secondary";
  error_summary?: string;
  provider_status?: string;
  validation_path?: string;
  langsmith_run_id?: string;
};

export type WorkflowTaskResult = {
  task_id: string;
  status: "success" | "failed" | "partial";
  output:
    | (Record<string, unknown> & {
        provenance?: {
          adapter?: string;
          operation?: string;
        };
      })
    | null;
};

export type AgentState = {
  is_interrupted: boolean;
  next: string[];
  values: {
    input_request: string;
    process_family: string;
    workflow_id: string;
    error_count: number;
    results: WorkflowTaskResult[];
    handoff_required: boolean;
    fatal_error: string;
    telemetry_logs?: TelemetryLog[];
  };
};

type EvidenceResponse = {
  filename: string;
  rows: Record<string, unknown>[];
  draft_summary?: Record<string, unknown>;
  report_md?: string;
};

interface WorkflowConsolePanelProps {
    threadId: string;
    token: string;
    API_BASE: string;
}

export default function WorkflowConsolePanel({ threadId, token, API_BASE }: WorkflowConsolePanelProps) {
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Evidence states
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null);
  const [isLoadingEvidence, setIsLoadingEvidence] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string|null>(null);

  // Review states
  const [reviewComment, setReviewComment] = useState("");
  const [isResuming, setIsResuming] = useState(false);
  
  // Telemetry Accordion
  const [isTelemetryOpen, setIsTelemetryOpen] = useState(false);
  const [showSecondaryLogs, setShowSecondaryLogs] = useState(false);

  const fetchEvidence = useCallback(async () => {
    if (!threadId || !token) return;
    setIsLoadingEvidence(true);
    setEvidenceError(null);
    try {
      const res = await fetch(`${API_BASE}/workflows/${threadId}/evidence`, {
          headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error("Failed to load evidence (404/500)");
      const data = await res.json();
      setEvidence(data);
    } catch(e: unknown) {
      setEvidenceError((e as Error).message);
    } finally {
      setIsLoadingEvidence(false);
    }
  }, [threadId, token, API_BASE]);

  // Restart polling when threadId changes
  useEffect(() => {
    setAgentState(null);
    setEvidence(null);
    setErrorMsg(null);
    setEvidenceError(null);
    setIsPolling(true);
  }, [threadId]);

  // Auto-fetch evidence if interrupted
  useEffect(() => {
    if (agentState?.is_interrupted && !evidence && !isLoadingEvidence && !evidenceError) {
      fetchEvidence();
    }
  }, [agentState?.is_interrupted, evidence, isLoadingEvidence, evidenceError, fetchEvidence]);

  // Polling Effect
  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    const fetchState = async () => {
      if (!threadId || !token) return;
      try {
        const res = await fetch(`${API_BASE}/workflows/${threadId}/state`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store"
        });

        if (res.status === 401 || res.status === 403) {
          setErrorMsg("Unauthorized access to this workflow.");
          setIsPolling(false);
          return;
        }

        if (!res.ok) {
          throw new Error(`State fetch failed: ${res.status}`);
        }

        const data: AgentState = await res.json();
        setAgentState(data);
        setErrorMsg(null);

        // Stop polling if interrupted or if pipeline has no next steps
        if (data.is_interrupted || data.next.length === 0) {
          setIsPolling(false);
        }

      } catch {
        console.error("Polling error occurred.");
      }
    };

    if (isPolling) {
      // Fetch immediately, then loop
      fetchState();
      intervalId = setInterval(fetchState, 2500);
    }

    return () => clearInterval(intervalId);
  }, [isPolling, threadId, token, API_BASE]);

  const handleResume = async (decision: "approve" | "handoff" | "request_changes") => {
    if (!threadId || !token || !agentState) return;
    
    const draftTask = (agentState.values?.results || []).find(r => r.task_id.startsWith("draft"));
    if (!draftTask) return;

    setIsResuming(true);
    try {
        const payload = {
            decision,
            comment: reviewComment,
            reviewer: "finance_manager_1",
            reviewed_at: new Date().toISOString(),
            reviewed_task_ids: [draftTask.task_id]
        };

        const res = await fetch(`${API_BASE}/workflows/${threadId}/resume`, {
            method: "POST",
            headers: { 
              "Content-Type": "application/json",
              "Authorization": `Bearer ${token}` 
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("Resume failed");

        setReviewComment("");
        setIsPolling(true);
    } catch (e: unknown) {
        setErrorMsg((e as Error).message);
    } finally {
        setIsResuming(false);
    }
  };

  const handleDownload = async () => {
    if (!threadId || !token) return;
    try {
        const res = await fetch(`${API_BASE}/workflows/${threadId}/download`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) throw new Error("Download failed");
        const blob = await res.blob();
        
        // Extract filename from Content-Disposition if available, or fallback
        const contentDisposition = res.headers.get('Content-Disposition');
        let filename = "download.zip";
        if (contentDisposition && contentDisposition.indexOf('filename=') !== -1) {
            const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
    } catch (err) {
        console.error("Download failed:", err);
        alert("다운로드에 실패했습니다.");
    }
  };


  const renderStatusBadge = (stepType: string) => {
    if (!agentState) return <span className="text-gray-400 p-2 border border-dashed text-sm">대기중</span>;
    
    const task = (agentState.values?.results || []).find(r => r.task_id.startsWith(stepType));
    if (!task) return <span className="text-gray-400 p-2 border border-dashed text-sm">대기중</span>;

    if (task.status === "success") 
        return <span className="flex items-center text-green-700 bg-green-50 px-2 py-1 border border-green-200"><CheckCircle2 className="w-4 h-4 mr-1"/> 성공</span>;
    if (task.status === "partial") 
        return <span className="flex items-center text-amber-700 bg-amber-50 px-2 py-1 border border-amber-200"><ShieldCheck className="w-4 h-4 mr-1"/> 부분 성공</span>;
    if (task.status === "failed") 
        return <span className="flex items-center text-red-700 bg-red-50 px-2 py-1 border border-red-200"><AlertCircle className="w-4 h-4 mr-1"/> 실패</span>;

    return null;
  };

  const isCompleted = agentState && agentState.next.length === 0 && !agentState.is_interrupted && (agentState.values?.results || []).some(r => r.task_id.startsWith("package") && r.status === "success");
  const packageTask = (agentState?.values?.results || []).find(r => r.task_id.startsWith("package"));
  const packagePath =
    typeof packageTask?.output?.package_path === "string"
      ? packageTask.output.package_path
      : null;

  return (
      <div className="space-y-6">
        {errorMsg && (
            <div className="bg-red-50 border border-red-200 text-red-700 p-4 shadow-sm">
                <strong>오류: </strong> {errorMsg}
            </div>
        )}

        <section className="bg-white border border-gray-200 p-6 shadow-sm">
            <div className="flex justify-between items-center mb-6">
                <div>
                   <h2 className="text-lg font-medium mb-1">에이전트 진행 흐름</h2>
                   {agentState?.values.input_request && (
                      <div className="text-sm text-gray-600 bg-gray-50 px-3 py-2 border border-gray-100 italic">
                        &quot;{agentState.values.input_request}&quot;
                      </div>
                   )}
                </div>
                {isPolling && <span className="flex items-center text-sm text-blue-600 font-medium"><Loader2 className="w-4 h-4 animate-spin mr-2"/> 실시간 동기화 중...</span>}
            </div>
            
            <div className="grid grid-cols-4 gap-4">
                {[
                    { id: 'collect', label: "데이터 수집" },
                    { id: 'normalize', label: "정규화 및 정제" },
                    { id: 'draft', label: "초안 작성 및 대사" },
                    { id: 'package', label: "최종 문서 패키징" }
                ].map((step, idx) => (
                    <div key={idx} className="border border-gray-200 p-4 bg-gray-50 flex flex-col items-start min-h-[100px]">
                        <span className="text-xs font-semibold text-gray-500 mb-2 mt-auto">단계 {idx+1}</span>
                        <div className="text-sm font-medium mb-4">{step.label}</div>
                        <div className="mt-auto">{renderStatusBadge(step.id)}</div>
                    </div>
                ))}
            </div>

            {agentState?.values.fatal_error && (
                <div className="mt-6 bg-red-50 p-4 border border-red-200 text-red-800 text-sm">
                    <strong>치명적인 구동 오류:</strong> {agentState.values.fatal_error}
                </div>
            )}
        </section>

        {/* Review Panel */}
        {agentState?.is_interrupted && (
        <section className="bg-blue-50 border border-blue-200 p-6 shadow-sm animate-in fade-in slide-in-from-bottom-2">
            <h2 className="text-lg font-medium text-blue-900 flex items-center mb-4">
                <Clock className="w-5 h-5 mr-2" />
                관리자 검토 필요 (Human-in-the-Loop)
            </h2>
            <div className="bg-white border border-blue-100 p-4 mb-4 shadow-sm">
                <p className="text-sm text-gray-700 mb-4 font-semibold border-b border-gray-100 pb-2">에이전트 초안 요약 (Draft Summary)</p>
                <div className="text-xs text-gray-800 mb-4">
                    {isLoadingEvidence ? (
                        <div className="flex items-center text-blue-600"><Loader2 className="w-4 h-4 animate-spin mr-2"/> 초안을 불러오는 중...</div>
                    ) : evidence?.draft_summary ? (
                        <div className="grid grid-cols-3 gap-3">
                           {Object.entries(evidence.draft_summary).map(([k, v]) => {
                               // Only render scalar values directly
                               if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
                                   return (
                                       <div key={k} className="border border-gray-100 p-2 bg-gray-50 rounded-sm">
                                           <div className="text-[10px] uppercase text-gray-500 font-semibold mb-1">{k.replace(/_/g, ' ')}</div>
                                           <div className="font-mono text-sm">{v}</div>
                                       </div>
                                   );
                               }
                               return null;
                           })}
                        </div>
                    ) : (
                        <span className="text-gray-400 italic">요약된 초안 데이터가 없습니다. 증빙을 확인하세요.</span>
                    )}
                </div>
            </div>

            <textarea 
                className="w-full border border-blue-200 p-3 text-sm focus:outline-none focus:border-blue-400 mb-4 bg-white shadow-inner"
                rows={3}
                placeholder="실행 코멘트 또는 필수 수정 사항을 추가하세요..."
                value={reviewComment}
                onChange={(e) => setReviewComment(e.target.value)}
            />

            <div className="flex gap-3">
                <button onClick={() => handleResume("approve")} disabled={isResuming} className="flex-1 bg-green-600 hover:bg-green-700 text-white px-4 py-2 font-medium disabled:opacity-50 transition-colors shadow-sm flex items-center justify-center">
                    <CheckCircle2 className="w-4 h-4 mr-2" /> 승인 (Approve)
                </button>
                <button onClick={() => handleResume("request_changes")} disabled={isResuming} className="flex-1 bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 font-medium disabled:opacity-50 transition-colors shadow-sm flex items-center justify-center">
                    <ShieldCheck className="w-4 h-4 mr-2" /> 수정 요청 (Request Changes)
                </button>
                <button onClick={() => handleResume("handoff")} disabled={isResuming} className="flex-1 bg-white border border-rose-300 text-rose-600 hover:bg-rose-50 px-4 py-2 font-medium disabled:opacity-50 transition-colors shadow-sm flex items-center justify-center">
                    <Activity className="w-4 h-4 mr-2" /> 외부 시스템 이관 (Handoff)
                </button>
            </div>
        </section>
        )}

        {/* Evidence Panel */}
        {agentState?.is_interrupted && (
        <section className="bg-white border border-gray-200 p-6 shadow-sm animate-in fade-in slide-in-from-bottom-2">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-medium flex items-center">
                   <FileCheck className="w-5 h-5 mr-2 text-gray-700" />
                   가공된 원천 데이터(Evidence) 미리보기
                </h2>
                {!evidence && (
                  <button onClick={fetchEvidence} disabled={isLoadingEvidence} className="bg-gray-100 hover:bg-gray-200 text-gray-800 px-3 py-1 text-sm border border-gray-300 font-medium whitespace-nowrap">
                      {isLoadingEvidence ? "불러오는 중..." : "데이터 불러오기"}
                  </button>
                )}
            </div>

            {evidenceError && <p className="text-red-600 text-sm mb-4">{evidenceError}</p>}
            
            {evidence && evidence.draft_summary && (
                <div className="mb-4 bg-gray-50 border border-gray-200 p-4">
                    <h3 className="text-sm font-semibold text-gray-700 border-b border-gray-200 pb-2 mb-2">통찰 및 초안 생성 요약</h3>
                    <pre className="text-xs text-gray-800 whitespace-pre-wrap font-mono">
                        {JSON.stringify(evidence.draft_summary, null, 2)}
                    </pre>
                </div>
            )}
            
            {evidence && evidence.rows.length > 0 && (
                <div className="overflow-x-auto border border-gray-200 text-sm">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                {Object.keys(evidence.rows[0]).map((col) => (
                                    <th key={col} className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {evidence.rows.map((row, i) => (
                                <tr key={i} className="hover:bg-gray-50">
                                    {Object.values(row).map((val: unknown, j) => (
                                        <td key={j} className="px-4 py-2 whitespace-nowrap text-gray-700">{String(val)}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="p-3 text-xs text-gray-500 bg-gray-50 border-t border-gray-200 flex justify-between">
                        <div>
                            <span className="mr-4">출처 데이터: <code className="bg-gray-200 text-gray-800 px-1 py-0.5">{evidence.filename}</code></span>
                            {(agentState?.values?.results || []).find(r => r.task_id.startsWith("collect"))?.output?.provenance?.adapter && (
                                <span className="inline-flex items-center">
                                    <span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span>
                                    활성화된 도메인 파서: <strong className="ml-1 text-blue-700">{(agentState.values?.results || []).find(r => r.task_id.startsWith("collect"))?.output?.provenance?.adapter}</strong>
                                </span>
                            )}
                        </div>
                        <span>총 데이터 행 수: <strong>{evidence.rows.length}</strong></span>
                    </div>
                </div>
            )}
        </section>
        )}
        
        {/* Conclusion Panel */}
        {isCompleted && (
        <section className="bg-green-50 border border-green-300 p-6 shadow-sm animate-in fade-in slide-in-from-bottom-2">
            <h2 className="text-lg font-medium text-green-900 flex items-center justify-between mb-4">
                <div className="flex items-center">
                    <CheckCircle2 className="w-5 h-5 mr-2" />
                    워크플로우 최종 완료
                </div>
                {!evidence && (
                  <button onClick={fetchEvidence} disabled={isLoadingEvidence} className="bg-white hover:bg-green-100 text-green-800 px-3 py-1 text-sm border border-green-300 font-medium whitespace-nowrap">
                      {isLoadingEvidence ? "불러오는 중..." : "최종 리포트 열기"}
                  </button>
                )}
            </h2>
            <div className="bg-white border border-green-200 p-4 space-y-4 text-sm text-gray-800">
                <div className="flex justify-between border-b border-gray-100 pb-2">
                    <span className="text-gray-500">수동 이관 여부(Handoff):</span>
                    <span className="font-mono">{agentState?.values.handoff_required ? 'TRUE' : 'FALSE'}</span>
                </div>
                
                {evidence && evidence.report_md && (
                    <div className="bg-gray-50 border border-gray-200 p-4 font-mono text-xs whitespace-pre-wrap">
                        {evidence.report_md}
                    </div>
                )}
                
                {packagePath && (
                    <div className="flex flex-col pt-2 border-t border-gray-100">
                        <span className="text-gray-500 mb-2">최종 결과물 패키지 경로:</span>
                        <div className="flex items-center space-x-2">
                            <code className="bg-gray-100 px-2 py-1 border border-gray-200 text-xs flex-1 overflow-hidden text-ellipsis">
                                {packagePath}
                            </code>
                            <button 
                                onClick={handleDownload}
                                className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 text-xs font-semibold whitespace-nowrap inline-flex items-center"
                            >
                                ZIP 다운로드
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </section>
        )}

        {/* Telemetry & Logs Panel */}
        {agentState?.values.telemetry_logs && agentState.values.telemetry_logs.length > 0 && (
        <section className="bg-white border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between border-b border-gray-200">
                <button 
                    onClick={() => setIsTelemetryOpen(!isTelemetryOpen)}
                    className="flex-1 flex justify-between items-center p-4 hover:bg-gray-50 focus:outline-none"
                >
                    <h2 className="text-sm font-medium flex items-center text-gray-800">
                        <Activity className="w-4 h-4 mr-2 text-gray-500" />
                        에이전트 텔레메트리 & 실시간 로그 ({agentState.values.telemetry_logs.filter(log => showSecondaryLogs || log.importance !== 'secondary').length})
                    </h2>
                    {isTelemetryOpen ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
                </button>
            </div>
            
            {isTelemetryOpen && (
                <div className="p-4 bg-gray-50">
                    <div className="flex justify-end mb-3">
                        <label className="flex items-center text-xs text-gray-500 cursor-pointer hover:text-gray-700">
                            <input 
                                type="checkbox" 
                                className="mr-2 rounded border-gray-300"
                                checked={showSecondaryLogs}
                                onChange={(e) => setShowSecondaryLogs(e.target.checked)}
                            />
                            시스템 내부 라우팅 로그 포함하기
                        </label>
                    </div>
                    <div className="space-y-3">
                        {[...agentState.values.telemetry_logs]
                            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()) // Time-series descending
                            .filter(log => showSecondaryLogs || log.importance !== "secondary")
                            .map((log, idx) => (
                            <div key={idx} className={`p-3 text-xs border ${log.status === 'error' ? 'bg-red-50 border-red-200' : log.importance === 'secondary' ? 'bg-gray-50 border-gray-100 opacity-80' : 'bg-white border-gray-200'}`}>
                                <div className="flex justify-between items-center mb-2">
                                    <span className="font-mono font-medium text-gray-700">
                                      {log.node} <span className="text-gray-400">|</span> {log.event}
                                      {log.importance === "secondary" && (
                                          <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-200 text-gray-600">EDGE</span>
                                      )}
                                    </span>
                                    <div className="flex space-x-3 text-gray-500">
                                        <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                                        <span>{log.latency_ms}ms</span>
                                        {log.status === 'error' ? (
                                            <span className="text-red-600 font-bold px-1 bg-red-100">ERR</span>
                                        ) : (
                                            <span className="text-green-600 font-bold px-1 bg-green-100">OK</span>
                                        )}
                                    </div>
                                </div>
                                {log.langsmith_run_id && (
                                    <div className="text-gray-500 mt-1 mb-2">Run ID: <code className="bg-gray-100 px-1">{log.langsmith_run_id}</code></div>
                                )}
                                {log.status === 'error' && (
                                    <div className="space-y-1 mt-2 p-2 bg-white border border-red-200 shadow-sm rounded-sm">
                                        {log.error_summary && <p className="text-red-700 font-medium"><strong>Summary:</strong> {log.error_summary}</p>}
                                        {log.validation_path && <p className="text-red-600 break-all"><strong>Path:</strong> {log.validation_path}</p>}
                                        {log.provider_status && <p className="text-red-600"><strong>Provider:</strong> {log.provider_status}</p>}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </section>
        )}
      </div>
  );
}
