"use client";

import { useState, useEffect, FormEvent } from "react";
import { Loader2, PlayCircle, ShieldCheck, LayoutList, AlertCircle, Paperclip, XCircle } from "lucide-react";
import WorkflowConsolePanel from "../../components/WorkflowConsolePanel";

type RegistryRow = {
  thread_id: string;
  workflow_id: string | null;
  owner_id: string;
  status: string;
  next_task: string | null;
  process_family: string | null;
  input_request_summary: string | null;
  last_error: string | null;
  updated_at: string;
};

export default function BoardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [workflows, setWorkflows] = useState<RegistryRow[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedThreads, setSelectedThreads] = useState<Set<string>>(new Set());
  
  const [filter, setFilter] = useState<string>("all");
  const [isQueueLoading, setIsQueueLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [confirmModal, setConfirmModal] = useState<{isOpen: boolean, message: string, onConfirm: () => void}>({isOpen: false, message: "", onConfirm: () => {}});

  // Clear selection on filter change
  useEffect(() => {
    setSelectedThreads(new Set());
  }, [filter]);

  // Start workflow form
  const [inputRequest, setInputRequest] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedHistoryFile, setSelectedHistoryFile] = useState<{file_id: string, original_filename: string, size_bytes: number} | null>(null);
  const [processFamilyOverride, setProcessFamilyOverride] = useState<string>("auto");
  const [isStarting, setIsStarting] = useState(false);
  const [startingMessage, setStartingMessage] = useState("");
  const [uploadingFileIndex, setUploadingFileIndex] = useState<number | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Metrics
  const [metrics, setMetrics] = useState<{total: number, running: number, interrupted: number, completed: number, error: number, deleted: number} | null>(null);

  // Recent Uploads History
  const [recentUploads, setRecentUploads] = useState<{file_id: string, original_filename: string, size_bytes: number, last_used_at: string}[]>([]);
  const [showRecentDropdown, setShowRecentDropdown] = useState(false);

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8001";

  const handleLogin = async () => {
    try {
      const res = await fetch("/api/auth/mock", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        setErrorMsg(null);
      } else {
        setErrorMsg("Dev Auth Route Failed.");
      }
    } catch {
      setErrorMsg("Failed to connect to dev auth route.");
    }
  };

  const [cursor, setCursor] = useState<string | null>(null);
  const LIMIT = 50;
  const [hasMore, setHasMore] = useState(true);

  const fetchQueue = async (reset: boolean = true) => {
    if (!token) return;
    setIsQueueLoading(true);
    
    const currentCursor = reset ? null : cursor;
    
    try {
        let url = `${API_BASE}/workflows?limit=${LIMIT}`;
        if (currentCursor) {
            url += `&cursor=${encodeURIComponent(currentCursor)}`;
        }
        if (filter === "deleted") url += `&status=deleted&include_deleted=true`;
        else if (filter === "interrupted") url += `&status=interrupted`;
        else if (filter === "completed") url += `&status=completed`;

        const res = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store"
        });

        if (res.status === 401 || res.status === 403) {
            setToken(null);
            throw new Error("Session expired. Please log in again.");
        }
        
        if (!res.ok) throw new Error("Failed to load workflow queue");

        const data = await res.json();
        const newWorkflows = data.workflows || [];
        
        if (reset) {
            setWorkflows(newWorkflows);
        } else {
            setWorkflows(prev => [...prev, ...newWorkflows]);
        }
        
        setCursor(data.next_cursor || null);
        setHasMore(!!data.next_cursor);
    } catch (e: unknown) {
        console.error(e);
        setErrorMsg((e as Error).message);
    } finally {
        setIsQueueLoading(false);
    }
  };

  const handleDeleteWorkflow = async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setConfirmModal({
          isOpen: true,
          message: "정말 이 워크플로우를 삭제하시겠습니까? (휴지통으로 이동합니다)",
          onConfirm: async () => {
              setConfirmModal(prev => ({...prev, isOpen: false}));
              try {
                  const res = await fetch(`${API_BASE}/workflows/${threadId}`, {
                      method: 'DELETE',
                      headers: { Authorization: `Bearer ${token}` }
                  });
                  if (!res.ok) {
                      const errBody = await res.json().catch(() => ({}));
                      throw new Error(errBody.detail || "삭제에 실패했습니다. (Running 상태인지 확인)");
                  }
                  
                  if (selectedThreadId === threadId) setSelectedThreadId(null);
                  // Refresh list locally
                  setWorkflows(prev => prev.filter(w => w.thread_id !== threadId));
              } catch (err: unknown) {
                  setErrorMsg((err as Error).message);
              }
          }
      });
  };

  const handleRestoreWorkflow = async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setConfirmModal({
          isOpen: true,
          message: "이 워크플로우를 이전 상태로 복구하시겠습니까?",
          onConfirm: async () => {
              setConfirmModal(prev => ({...prev, isOpen: false}));
              try {
                  const res = await fetch(`${API_BASE}/workflows/${threadId}/restore`, {
                      method: 'POST',
                      headers: { Authorization: `Bearer ${token}` }
                  });
                  if (!res.ok) {
                      const errBody = await res.json().catch(() => ({}));
                      throw new Error(errBody.detail || "복구에 실패했습니다.");
                  }
                  
                  if (selectedThreadId === threadId) setSelectedThreadId(null);
                  // Refresh list locally
                  setWorkflows(prev => prev.filter(w => w.thread_id !== threadId));
              } catch (err: unknown) {
                  setErrorMsg((err as Error).message);
              }
          }
      });
  };

  const handleBatchAction = async (action: "delete" | "restore" | "purge", targetIds?: Set<string>) => {
      const idsToProcess = targetIds || selectedThreads;
      if (idsToProcess.size === 0) return;
      
      let confirmMsg = "";
      if (action === "delete") confirmMsg = `선택한 ${idsToProcess.size}개의 항목을 삭제하시겠습니까?`;
      if (action === "restore") confirmMsg = `선택한 ${idsToProcess.size}개의 항목을 복구하시겠습니까?`;
      if (action === "purge") confirmMsg = `경고: 선택한 ${idsToProcess.size}개의 항목을 영구 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`;
      
      setConfirmModal({
          isOpen: true,
          message: confirmMsg,
          onConfirm: async () => {
              setConfirmModal(prev => ({...prev, isOpen: false}));
              try {
                  const res = await fetch(`${API_BASE}/workflows/batch`, {
                      method: 'POST',
                      headers: { 
                          'Content-Type': 'application/json',
                          Authorization: `Bearer ${token}` 
                      },
                      body: JSON.stringify({
                          action,
                          thread_ids: Array.from(idsToProcess)
                      })
                  });
                  
                  if (!res.ok) {
                      const errBody = await res.json().catch(() => ({}));
                      throw new Error(errBody.detail || "일괄 처리 요청에 실패했습니다.");
                  }
                  
                  // Clear selection and refresh list
                  if (selectedThreadId && idsToProcess.has(selectedThreadId)) {
                      setSelectedThreadId(null);
                  }
                  setSelectedThreads(new Set());
                  fetchQueue(true);
              } catch (err: unknown) {
                  setErrorMsg((err as Error).message);
              }
          }
      });
  };

  const toggleSelection = (threadId: string) => {
      setSelectedThreads(prev => {
          const newSet = new Set(prev);
          if (newSet.has(threadId)) newSet.delete(threadId);
          else newSet.add(threadId);
          return newSet;
      });
  };

  const fetchAllDeletedThreadIds = async (): Promise<string[]> => {
      if (!token) return [];

      const allIds: string[] = [];
      let nextCursor: string | null = null;

      do {
          let url = `${API_BASE}/workflows?limit=100&status=deleted&include_deleted=true`;
          if (nextCursor) {
              url += `&cursor=${encodeURIComponent(nextCursor)}`;
          }

          const res = await fetch(url, {
              headers: { Authorization: `Bearer ${token}` },
              cache: "no-store"
          });

          if (!res.ok) {
              throw new Error("휴지통 목록을 불러오지 못했습니다.");
          }

          const data = await res.json();
          const deletedRows: RegistryRow[] = data.workflows || [];
          allIds.push(...deletedRows.map((wf) => wf.thread_id));
          nextCursor = data.next_cursor || null;
      } while (nextCursor);

      return allIds;
  };

  const chunkThreadIds = (threadIds: string[], chunkSize: number): string[][] => {
      const chunks: string[][] = [];
      for (let i = 0; i < threadIds.length; i += chunkSize) {
          chunks.push(threadIds.slice(i, i + chunkSize));
      }
      return chunks;
  };

  const fetchRecentUploads = async () => {
      if (!token) return;
      try {
          const res = await fetch(`${API_BASE}/workflows/uploads`, {
              headers: { Authorization: `Bearer ${token}` }
          });
          if (res.ok) {
              const data = await res.json();
              setRecentUploads(data.uploads || []);
          }
      } catch (e) {
          console.error("Failed to fetch recent uploads", e);
      }
  };

  const fetchMetrics = async () => {
      if (!token) return;
      try {
          const res = await fetch(`${API_BASE}/workflows/metrics`, {
              headers: { Authorization: `Bearer ${token}` },
              cache: "no-store"
          });
          if (res.ok) {
              const data = await res.json();
              setMetrics(data);
          }
      } catch (e) {
          console.error("Failed to fetch metrics", e);
      }
  };

  useEffect(() => {
    if (token) {
        fetchQueue(true);
        fetchRecentUploads();
        fetchMetrics();
        // Refresh queue and metrics every 10 seconds to catch registry updates
        const interval = setInterval(() => {
            fetchQueue(true);
            fetchMetrics();
        }, 10000);
        return () => clearInterval(interval);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filter]);

  const handleStart = async (e: FormEvent) => {
    e.preventDefault();
    if (!inputRequest.trim()) {
      setErrorMsg("작업을 실행하려면 지시사항(프롬프트)을 입력해주세요.");
      return;
    }
    if (!token) {
      setErrorMsg("인증 정보가 없습니다. 새로고침 후 다시 시도해주세요.");
      return;
    }

    setIsStarting(true);
    setStartingMessage("작업 초기화 중...");
    setUploadingFileIndex(null);
    setErrorMsg(null);

    try {
      const source_file_ids: string[] = [];
      
      if (selectedFiles.length > 0) {
        for (let i = 0; i < selectedFiles.length; i++) {
            const file = selectedFiles[i];
            setUploadingFileIndex(i);
            setStartingMessage(`증빙 자료 업로드 중 (${i + 1}/${selectedFiles.length})`);
            const formData = new FormData();
            formData.append("file", file);
            const upRes = await fetch(`${API_BASE}/workflows/upload`, {
              method: "POST",
              headers: {
                "Authorization": `Bearer ${token}`
              },
              body: formData
            });
            
            if (!upRes.ok) {
              try {
                const errBody = await upRes.json();
                throw new Error(`File upload failed for ${file.name}: ${errBody.detail || 'Unknown error'}`);
              } catch {
                throw new Error(`File upload failed for ${file.name} with status ${upRes.status}`);
              }
            }
            
            const upData = await upRes.json();
            source_file_ids.push(upData.file_id);
        }
        fetchRecentUploads();
        setUploadingFileIndex(null);
      } else if (selectedHistoryFile) {
        source_file_ids.push(selectedHistoryFile.file_id);
      }

      const payload: {
        input_request: string;
        source_file_ids?: string[];
        process_family_override?: string;
      } = { input_request: inputRequest };
      if (source_file_ids.length > 0) payload.source_file_ids = source_file_ids;
      if (processFamilyOverride !== "auto") payload.process_family_override = processFamilyOverride;

      setStartingMessage("AI 분석 및 워크플로우 대기열 등록 중...");

      const res = await fetch(`${API_BASE}/workflows/start`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}` 
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error("Failed to start workflow");

      const data = await res.json();
      setInputRequest("");
      setSelectedFiles([]);
      setSelectedHistoryFile(null);
      
      // OPTIMISTIC UPDATE: Inject the new workflow into state immediately to avoid
      // asynchronous race conditions with the E2E framework relying on UI presence
      const newCard: RegistryRow = {
          thread_id: data.job_id,
          workflow_id: null,
          owner_id: "finance_manager_1",
          status: "running", // Backend will set it to 'running' mostly initially
          next_task: null,
          process_family: "unclassified",
          input_request_summary: inputRequest.substring(0, 50),
          last_error: null,
          updated_at: new Date().toISOString()
      };
      setWorkflows(prev => [newCard, ...prev]);

      // Immediately refresh queue to show the new record and full DB sync later
      fetchQueue(true);
      // Auto-select the newly started workflow
      setSelectedThreadId(data.job_id);
    } catch (e: unknown) {
      setErrorMsg((e as Error).message);
    } finally {
      setIsStarting(false);
      setStartingMessage("");
      setUploadingFileIndex(null);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-8">
        <div className="bg-white p-8 border border-gray-200 max-w-sm w-full text-center shadow-sm">
            <ShieldCheck className="w-12 h-12 text-indigo-600 mx-auto mb-4" />
            <h1 className="text-xl font-medium text-gray-900 mb-2">Agentic 시스템 인증</h1>
            <p className="text-sm text-gray-500 mb-6">워크플로우 조정을 위한 로그인이 필요합니다.</p>
            {errorMsg && <div className="p-3 mb-6 bg-red-50 text-red-700 border border-red-200 text-sm text-left">{errorMsg}</div>}
            <button onClick={handleLogin} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 px-4 transition-colors">
                검토자(Reviewer)로 계속하기
            </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 font-sans text-gray-900">
        
        {/* Top Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between z-10 shadow-sm relative">
            <div className="flex items-center gap-3">
                <ShieldCheck className="w-6 h-6 text-indigo-600" />
                <h1 className="text-xl font-semibold tracking-tight">Agentic 통합 관제 콘솔</h1>
            </div>
            <button onClick={() => { setToken(null); setSelectedThreadId(null); }} className="text-sm text-gray-500 hover:text-gray-900 underline">
                로그아웃
            </button>
        </header>

        {errorMsg && (
            <div className="mx-6 mt-4 bg-red-50 border border-red-200 text-red-700 p-4 shadow-sm flex items-center gap-2 text-sm max-w-4xl">
               <AlertCircle className="w-4 h-4"/> <strong>Error: </strong> {errorMsg}
            </div>
        )}

        {/* Top KPI Metrics Bar */}
        {metrics && (
            <div className="mx-6 mt-4 grid grid-cols-5 gap-4">
                <div className="bg-white border border-gray-200 p-4 shadow-sm relative overflow-hidden">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">Total Active</div>
                    <div className="text-2xl font-medium text-gray-900">{metrics.total}</div>
                </div>
                <div className="bg-white border border-gray-200 p-4 shadow-sm relative overflow-hidden border-t-4 border-t-amber-400">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">실행중 (Running)</div>
                    <div className="text-2xl font-medium text-amber-600">{metrics.running}</div>
                </div>
                <div className="bg-white border border-gray-200 p-4 shadow-sm relative overflow-hidden border-t-4 border-t-blue-400">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">검토대기 (Review)</div>
                    <div className="text-2xl font-medium text-blue-600">{metrics.interrupted}</div>
                </div>
                <div className="bg-white border border-gray-200 p-4 shadow-sm relative overflow-hidden border-t-4 border-t-green-400">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">성공 (Completed)</div>
                    <div className="text-2xl font-medium text-green-600">{metrics.completed}</div>
                </div>
                <div className="bg-white border border-gray-200 p-4 shadow-sm relative overflow-hidden border-t-4 border-t-red-400">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">오류 (Errors)</div>
                    <div className="text-2xl font-medium text-red-600">{metrics.error}</div>
                </div>
            </div>
        )}

        <div className="flex-1 flex overflow-hidden mt-4">
            {/* Left Sidebar: Queue Board */}
            <div className="w-1/3 flex flex-col bg-gray-50 border-r border-gray-200">
                {/* Board Controls */}
                <div className="p-4 border-b border-gray-200 bg-white shadow-sm z-10">
                    <div className="flex justify-between items-center mb-3">
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">새 작업 지시하기</h2>
                        <button 
                            type="button" 
                            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                            onClick={() => setShowRecentDropdown(!showRecentDropdown)}
                        >
                            {showRecentDropdown ? "닫기" : "최근 업로드"}
                        </button>
                    </div>
                    {showRecentDropdown && recentUploads.length > 0 && (
                        <div className="mb-3 border border-indigo-100 bg-white shadow-sm overflow-hidden text-xs absolute z-50 w-[300px] max-h-[200px] overflow-y-auto">
                            <div className="bg-indigo-50 px-3 py-2 font-medium text-indigo-800 border-b border-indigo-100 sticky top-0">최근 업로드 이력</div>
                            {recentUploads.map(up => (
                                <div 
                                    key={up.file_id} 
                                    className="px-3 py-2 border-b border-gray-100 hover:bg-gray-50 cursor-pointer flex justify-between items-center"
                                    onClick={() => {
                                        setSelectedHistoryFile(up);
                                        setSelectedFiles([]);
                                        setShowRecentDropdown(false);
                                    }}
                                >
                                    <span className="truncate flex-1 mr-2">{up.original_filename}</span>
                                    <span className="text-gray-400 shrink-0">{(up.size_bytes / 1024).toFixed(1)} KB</span>
                                </div>
                            ))}
                        </div>
                    )}
                    <div
                        onDragOver={(e) => {
                            e.preventDefault();
                            setIsDragOver(true);
                        }}
                        onDragLeave={() => setIsDragOver(false)}
                        onDrop={(e) => {
                            e.preventDefault();
                            setIsDragOver(false);
                            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                                setSelectedFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]);
                            }
                        }}
                        className={`transition-colors rounded-sm ${isDragOver ? "bg-indigo-50 border-2 border-dashed border-indigo-300 p-2 -m-2 mb-1" : ""}`}
                    >
                        <form onSubmit={handleStart} className="flex flex-col gap-3">
                            <div className="flex gap-2">
                                <label
                                    className="relative flex w-[40px] shrink-0 cursor-pointer items-center justify-center border border-gray-300 bg-white p-2 text-gray-400 shadow-sm transition-colors hover:bg-indigo-50 hover:text-indigo-600"
                                    title="첨부파일 (엑셀/CSV/PDF, 파일 Drag & Drop 및 이미지 영수증 지원)"
                                >
                                    <input
                                        type="file"
                                        className="hidden"
                                        accept=".xlsx,.csv,.pdf,.jpg,.jpeg,.png"
                                        multiple
                                        onChange={(e) => {
                                            if (e.target.files) {
                                                setSelectedFiles(prev => [...prev, ...Array.from(e.target.files!)]);
                                            }
                                        }}
                                        disabled={isStarting}
                                    />
                                    <Paperclip className="h-4 w-4" />
                                </label>
                                <select
                                    className="shrink-0 border border-gray-300 bg-white px-2 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-100"
                                    value={processFamilyOverride}
                                    onChange={(e) => setProcessFamilyOverride(e.target.value)}
                                    disabled={isStarting}
                                >
                                    <option value="auto">Auto (AI 추론)</option>
                                    <option value="treasury">자금/일정</option>
                                    <option value="withholding">원천세</option>
                                    <option value="payroll">급여대장</option>
                                    <option value="grant">보조금</option>
                                </select>
                                <input
                                    type="text"
                                    disabled={isStarting}
                                    placeholder="예: 이번 달 급여대장 엑셀 파일 검증해줘"
                                    value={inputRequest}
                                    onChange={(e) => setInputRequest(e.target.value)}
                                    className="flex-1 border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-gray-100"
                                />
                                <button
                                    type="submit"
                                    disabled={isStarting || !inputRequest}
                                    className="flex items-center bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:bg-gray-400 whitespace-nowrap"
                                >
                                    {isStarting ? (
                                        <>
                                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                            실행 중
                                        </>
                                    ) : (
                                        <>
                                            <PlayCircle className="h-4 w-4 mr-2" />
                                            업로드 및 분석 실행
                                        </>
                                    )}
                                </button>
                            </div>

                            {selectedFiles.length > 0 && (
                                <div className="flex flex-col gap-1 border border-indigo-100 bg-indigo-50 p-2 text-xs text-indigo-800 shadow-sm">
                                    <div className="flex justify-between font-semibold border-b border-indigo-100 pb-1 mb-1">
                                        <span>첨부된 증빙자료 ({selectedFiles.length}건)</span>
                                        {!isStarting && (
                                            <button type="button" onClick={() => setSelectedFiles([])} className="text-indigo-600 hover:text-indigo-800 focus:outline-none">
                                                모두 지우기
                                            </button>
                                        )}
                                    </div>
                                    {selectedFiles.map((f, idx) => (
                                        <div key={idx} className="flex flex-row flex-wrap items-center justify-between pb-1">
                                            <div className="flex items-center gap-2 overflow-hidden">
                                                {isStarting && uploadingFileIndex === idx ? (
                                                    <Loader2 className="h-3 w-3 shrink-0 animate-spin text-indigo-600" />
                                                ) : isStarting && (uploadingFileIndex === null || idx < uploadingFileIndex) ? (
                                                    <ShieldCheck className="h-3 w-3 shrink-0 text-emerald-500" />
                                                ) : (
                                                    <Paperclip className="h-3 w-3 shrink-0 text-indigo-500" />
                                                )}
                                                <span className="truncate font-medium">{f.name}</span>
                                                <span className="shrink-0 text-indigo-400">({(f.size / 1024).toFixed(1)} KB)</span>
                                            </div>
                                            {!isStarting && (
                                                <button
                                                    type="button"
                                                    onClick={() => setSelectedFiles(prev => prev.filter((_, i) => i !== idx))}
                                                    className="shrink-0 text-indigo-400 hover:text-indigo-700 focus:outline-none"
                                                    title="첨부 취소"
                                                >
                                                    <XCircle className="h-4 w-4" />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {selectedHistoryFile && selectedFiles.length === 0 && (
                                <div className="flex items-center justify-between border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 shadow-sm">
                                    <div className="flex items-center gap-2 overflow-hidden">
                                        {isStarting ? (
                                            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                                        ) : (
                                            <LayoutList className="h-3 w-3 shrink-0 text-emerald-500" />
                                        )}
                                        <span className="truncate font-medium">{selectedHistoryFile.original_filename}</span>
                                        <span className="shrink-0 text-emerald-400">(재사용 내역)</span>
                                    </div>
                                    {!isStarting && (
                                        <button
                                            type="button"
                                            onClick={() => setSelectedHistoryFile(null)}
                                            className="ml-2 shrink-0 text-emerald-400 hover:text-emerald-700 focus:outline-none"
                                            title="재사용 취소"
                                        >
                                            <XCircle className="h-4 w-4" />
                                        </button>
                                    )}
                                </div>
                            )}

                            {isStarting && (
                                <p className="animate-pulse text-xs font-medium text-indigo-600">
                                    {startingMessage}
                                </p>
                            )}
                        </form>
                    </div>

                    <div className="mt-6 mb-2 flex items-center justify-between">
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">작업 대기열 기록</h2>
                        {isQueueLoading && <Loader2 className="h-3 w-3 animate-spin text-gray-400" />}
                    </div>
                    
                    <div className="flex gap-2 text-xs">
                        {[
                            { id: 'all', label: '전체' }, 
                            { id: 'interrupted', label: '검토대기' }, 
                            { id: 'completed', label: '종료됨' },
                            { id: 'deleted', label: '휴지통' }
                        ].map((f) => (
                            <button 
                                key={f.id}
                                onClick={() => setFilter(f.id)}
                                className={`px-3 py-1 rounded-full border border-gray-200 transition-colors ${filter === f.id ? 'bg-indigo-100 text-indigo-700 border-indigo-200 font-medium' : 'bg-gray-50 text-gray-600 hover:bg-gray-100'}`}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>
                    {/* Floating Action Bar */}
                    {selectedThreads.size > 0 && (
                        <div className="mt-4 flex items-center justify-between bg-indigo-50 border border-indigo-200 px-3 py-2 rounded-sm sticky top-0 z-10 shadow-sm">
                            <span className="text-xs font-semibold text-indigo-700">{selectedThreads.size}개 선택됨</span>
                            <div className="flex gap-2 relative">
                                {filter === 'deleted' ? (
                                    <>
                                        <button 
                                            onClick={() => handleBatchAction('restore')}
                                            className="text-[11px] bg-white border border-indigo-200 text-indigo-700 px-2 py-1 hover:bg-indigo-100 rounded-sm font-medium"
                                        >
                                            일괄 복구
                                        </button>
                                        <button 
                                            onClick={() => handleBatchAction('purge')}
                                            className="text-[11px] bg-red-50 border border-red-200 text-red-700 px-2 py-1 hover:bg-red-100 rounded-sm font-medium"
                                        >
                                            선택 영구삭제
                                        </button>
                                    </>
                                ) : (
                                    <button 
                                        onClick={() => handleBatchAction('delete')}
                                        className="text-[11px] bg-white border border-rose-200 text-rose-700 px-2 py-1 hover:bg-rose-50 rounded-sm font-medium"
                                    >
                                        일괄 삭제
                                    </button>
                                )}
                            </div>
                        </div>
                    )}
                    {filter === 'deleted' && workflows.length > 0 && selectedThreads.size === 0 && (
                        <div className="mt-4 flex justify-end">
                            <button 
                                onClick={async () => {
                                    setSelectedThreads(new Set(workflows.map(w => w.thread_id)));
                                    // Hack: We want to call batch action, but setState is async. So pass explicitly.
                                    const confirmMsg = `경고: 휴지통의 모든 항목(${workflows.length}개)을 영구 삭제하시겠습니까?`;
                                    setConfirmModal({
                                        isOpen: true,
                                        message: confirmMsg,
                                        onConfirm: async () => {
                                            setConfirmModal(prev => ({...prev, isOpen: false}));
                                            try {
                                                const allDeletedIds = await fetchAllDeletedThreadIds();

                                                if (allDeletedIds.length === 0) {
                                                    setSelectedThreads(new Set());
                                                    setSelectedThreadId(null);
                                                    fetchQueue(true);
                                                    return;
                                                }

                                                for (const batchIds of chunkThreadIds(allDeletedIds, 100)) {
                                                    const res = await fetch(`${API_BASE}/workflows/batch`, {
                                                        method: 'POST',
                                                        headers: {
                                                            'Content-Type': 'application/json',
                                                            Authorization: `Bearer ${token}`
                                                        },
                                                        body: JSON.stringify({
                                                            action: 'purge',
                                                            thread_ids: batchIds
                                                        })
                                                    });

                                                    if (!res.ok) {
                                                        throw new Error("일괄 처리 요청에 실패했습니다.");
                                                    }
                                                }

                                                setSelectedThreads(new Set());
                                                setSelectedThreadId(null);
                                                fetchQueue(true);
                                        } catch (err: unknown) {
                                            setErrorMsg((err as Error).message);
                                        }
                                    }});
                                }}
                                className="text-[11px] flex items-center gap-1 bg-white border border-red-200 text-red-600 px-2 py-1 hover:bg-red-50 transition-colors"
                            >
                                <XCircle className="w-3 h-3"/> 휴지통 비우기
                            </button>
                        </div>
                    )}
                </div>

                {/* Queue List */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {workflows.map(wf => (
                        <div 
                            key={wf.thread_id} 
                            onClick={() => setSelectedThreadId(wf.thread_id)}
                            data-testid="workflow-card"
                            data-thread-id={wf.thread_id}
                            className={`p-4 pl-12 border bg-white cursor-pointer transition-all relative ${selectedThreadId === wf.thread_id ? 'border-indigo-500 ring-1 ring-indigo-500 shadow-md' : 'border-gray-200 hover:border-gray-300 shadow-sm hover:shadow-md'}`}
                        >
                            <div className="absolute left-4 top-4" onClick={(e) => e.stopPropagation()}>
                                <input 
                                    type="checkbox" 
                                    className="w-4 h-4 text-indigo-600 cursor-pointer rounded-sm border-gray-300 focus:ring-indigo-500"
                                    checked={selectedThreads.has(wf.thread_id)}
                                    onClick={(e) => e.stopPropagation()}
                                    onChange={() => toggleSelection(wf.thread_id)}
                                />
                            </div>

                            {filter === 'deleted' ? (
                                <button 
                                    onClick={(e) => handleRestoreWorkflow(wf.thread_id, e)}
                                    className="absolute top-3 right-3 text-gray-400 hover:text-emerald-500 transition-colors"
                                    title="복구"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path></svg>
                                </button>
                            ) : (
                                <button 
                                    onClick={(e) => handleDeleteWorkflow(wf.thread_id, e)}
                                    className="absolute top-3 right-3 text-gray-300 hover:text-red-500 transition-colors"
                                    title="삭제"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                </button>
                            )}
                            <div className="flex justify-between items-start mb-2 pr-6">
                                <div className="flex gap-2 items-center flex-wrap">
                                    <span className={`text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-sm ${
                                        wf.status === 'interrupted' ? 'bg-blue-100 text-blue-700' :
                                        wf.status === 'completed' ? 'bg-green-100 text-green-700' :
                                        wf.status === 'error' ? 'bg-red-100 text-red-700' :
                                        'bg-amber-100 text-amber-700'
                                    }`}>
                                        {wf.status}
                                    </span>
                                    {wf.process_family && (
                                        <span className="text-[10px] font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-sm border border-indigo-100" data-testid="process-family-badge">
                                            {wf.process_family.toUpperCase()}
                                        </span>
                                    )}
                                </div>
                                <span className="text-[10px] text-gray-400 uppercase font-mono shrink-0">
                                    {wf.thread_id.split('-')[0]}
                                </span>
                            </div>
                            <div className="text-sm font-medium text-gray-800 line-clamp-2 mb-1">
                                {wf.input_request_summary || "알 수 없는 요청"}
                            </div>
                            <div className="flex justify-between items-center text-xs text-gray-500 mt-3 pt-2 border-t border-gray-50">
                                <span className="font-mono bg-gray-100 px-1 py-0.5">{wf.next_task || '없음'}</span>
                                <span>{new Date(wf.updated_at).toLocaleTimeString()}</span>
                            </div>
                        </div>
                    ))}
                    
                    {workflows.length > 0 && hasMore && (
                        <button 
                            onClick={() => fetchQueue(false)}
                            className="w-full py-2 mt-2 text-xs font-semibold text-gray-500 bg-gray-100 hover:bg-gray-200 rounded-sm transition-colors"
                        >
                            더 불러오기
                        </button>
                    )}
                    
                    {workflows.length === 0 && !isQueueLoading && (
                        <div className="text-center p-8 text-gray-400 text-sm italic">
                            현재 대기열에 조건에 맞는 워크플로우가 없습니다.
                        </div>
                    )}
                </div>
            </div>

            {/* Custom Confirm Modal */}
            {confirmModal.isOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm transition-all animate-in fade-in duration-200">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md border border-gray-100 overflow-hidden transform animate-in zoom-in-95 duration-200">
                        <div className="p-6">
                            <div className="flex items-center gap-3 mb-4 text-red-600">
                                <AlertCircle className="w-6 h-6" />
                                <h3 className="text-lg font-bold text-gray-900">확인</h3>
                            </div>
                            <p className="text-sm text-gray-600 leading-relaxed">
                                {confirmModal.message}
                            </p>
                        </div>
                        <div className="bg-gray-50 px-6 py-4 flex justify-end gap-2 border-t border-gray-100">
                            <button
                                onClick={() => setConfirmModal({isOpen: false, message: "", onConfirm: () => {}})}
                                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 transition-colors"
                            >
                                취소
                            </button>
                            <button
                                onClick={confirmModal.onConfirm}
                                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
                            >
                                확인
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Right Main Content: Detail View */}
            <div className="flex-1 bg-gray-100 overflow-y-auto relative">
                {selectedThreadId ? (
                    <div className="p-8 max-w-4xl mx-auto pb-24">
                        <div className="mb-6 flex items-center justify-between bg-white px-4 py-3 border border-gray-200 shadow-sm text-sm">
                           <span className="text-gray-500">현재 작업 쓰레드 ID (Thread): <strong className="font-mono bg-gray-100 px-1 py-0.5 text-gray-800">{selectedThreadId}</strong></span>
                        </div>
                        <WorkflowConsolePanel 
                            threadId={selectedThreadId} 
                            token={token} 
                            API_BASE={API_BASE}
                        />
                    </div>
                ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
                        <LayoutList className="w-16 h-16 text-gray-300 mb-4" />
                        <h2 className="text-lg font-medium text-gray-500">대기열에서 워크플로우를 선택하세요</h2>
                        <p className="text-sm mt-2">이곳에서 상세 진행 흐름과 원천 데이터(Evidence)를 검토할 수 있습니다.</p>
                    </div>
                )}
            </div>
        </div>
    </div>
  );
}
