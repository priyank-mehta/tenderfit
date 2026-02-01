import { useRef, useState } from "react";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

const stages = [
  { id: "scout", label: "Scout" },
  { id: "collector", label: "Collector" },
  { id: "extractor", label: "Extractor" },
  { id: "verifier-a", label: "Verifier A" },
  { id: "verifier-b", label: "Verifier B" },
  { id: "verifier-c", label: "Verifier C" },
  { id: "arbiter", label: "Arbiter" },
  { id: "shortlist", label: "Shortlist" },
];

const laneStages = ["collector", "extractor", "verifier-a", "verifier-b", "verifier-c", "arbiter"];

const stepMeta = [
  {
    id: 0,
    label: "Scout",
    title: "Scout / Scan",
    helper:
      "Query BidPlus and refine with LLM filters. This writes listings under artifacts/<bid_id>/listing.json.",
  },
  {
    id: 1,
    label: "Collect",
    title: "Collector",
    helper: "Live pipeline + logs only. Start a fetch job and inspect per-bid traces.",
  },
  {
    id: 2,
    label: "Evaluate",
    title: "Evaluator",
    helper: "Live pipeline + logs only. Run extract/verify/arbiter with citations.",
  },
  {
    id: 3,
    label: "Shortlist",
    title: "Arbiter & Shortlist",
    helper: "Arbiter progress, final report, and top-ranked shortlist.",
  },
];

const makeLane = () => ({
  stages: Object.fromEntries(laneStages.map((stage) => [stage, "idle"])),
  logs: [],
  currentStage: "queued",
});

export default function App() {
  const [step, setStep] = useState(0);
  const [maxStep, setMaxStep] = useState(0);
  const [activeJobType, setActiveJobType] = useState(null);
  const [pipelineState, setPipelineState] = useState(
    Object.fromEntries(stages.map((stage) => [stage.id, "idle"]))
  );
  const [logsScan, setLogsScan] = useState([]);
  const [logsCollect, setLogsCollect] = useState([]);
  const [logsEval, setLogsEval] = useState([]);
  const [message, setMessage] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [result, setResult] = useState(null);
  const [metrics, setMetrics] = useState({ decision: "—", score: "—", best: "—" });
  const [arbiterProgress, setArbiterProgress] = useState(0);
  const [arbiterStatus, setArbiterStatus] = useState("Waiting for evaluation output...");
  const [reportPreview, setReportPreview] = useState("");
  const [shortlistPreview, setShortlistPreview] = useState("");
  const [shortlistRows, setShortlistRows] = useState([]);
  const [bestRow, setBestRow] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [laneState, setLaneState] = useState({});
  const [laneOrder, setLaneOrder] = useState([]);
  const [runAllActive, setRunAllActive] = useState(false);
  const [runAllMessage, setRunAllMessage] = useState("");
  const [toast, setToast] = useState(null);
  const [narrative, setNarrative] = useState([]);
  const [remark, setRemark] = useState("");
  const [shortlistEmpty, setShortlistEmpty] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState("examples/company_profile.example.json");
  const eventSourceRef = useRef(null);
  const runAllSourcesRef = useRef({});
  const runAllRef = useRef({ pendingEvals: 0, pendingCollectors: 0 });

  const [scanForm, setScanForm] = useState({
    keywords: "cabs taxi",
    days: 2,
    top: 5,
    maxPages: 2,
    llmFilter: true,
    forceRefresh: false,
    llmMaxCandidates: 5,
    llmBatchSize: 5,
  });
  const [fetchForm, setFetchForm] = useState({
    bidId: "",
    cacheDir: "/tmp/tenderfit_collect_cache2",
  });
  const [evalForm, setEvalForm] = useState({
    bidId: "",
    companyPath: "examples/company_profile.example.json",
  });
  const [shortlistForm, setShortlistForm] = useState({
    top: 10,
    companyPath: "examples/company_profile.example.json",
  });
  const profileOptions = [
    { value: "examples/company_profile.example.json", label: "Demo Fleet Services" },
    { value: "examples/company_profile.midsize.json", label: "Midsize Mobility Co" },
    { value: "examples/company_profile.enterprise.json", label: "Enterprise Transit Group" },
  ];

  const loadProfile = async (path) => {
    const response = await fetch(`${API_BASE}/api/files?path=${encodeURIComponent(path)}`);
    if (!response.ok) return;
    const payload = await response.json();
    try {
      const parsed = JSON.parse(payload.content || "{}");
      setProfileData(parsed);
    } catch {
      setProfileData(null);
    }
  };

  const runJob = async (endpoint, payload) => {
    setMessage("");
    setActiveJobType(endpoint);
    resetPipeline();
    if (endpoint === "scan") {
      setStep(0);
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    if (endpoint === "evaluate" || endpoint === "shortlist") {
      setArbiterProgress(25);
      setArbiterStatus("Arbiter queued. Waiting for verifier quorum...");
    }

    const response = await fetch(`${API_BASE}/api/jobs/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      setMessage(data.detail || "Request failed.");
      return;
    }
    const source = new EventSource(`${API_BASE}/api/jobs/${data.job_id}/events`);
    eventSourceRef.current = source;
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      handleEvent(payload, endpoint);
    };
  };

  const startJob = async (endpoint, payload, onEvent) => {
    console.info("[UI] startJob", endpoint, payload);
    const response = await fetch(`${API_BASE}/api/jobs/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    console.info("[UI] startJob response", endpoint, response.status);
    const data = await response.json();
    if (!response.ok) {
      console.error("[UI] startJob failed", endpoint, data);
      throw new Error(data.detail || "Request failed.");
    }
    const source = new EventSource(`${API_BASE}/api/jobs/${data.job_id}/events`);
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      console.debug("[UI] event", endpoint, payload);
      onEvent(payload);
    };
    return { jobId: data.job_id, source };
  };

  const handleEvent = (event, jobType) => {
    if (event.type === "log") {
      appendLog(event.line, jobType);
    }
    if (event.type === "stage") {
      setPipelineState((prev) => ({ ...prev, [event.stage]: event.status }));
      if (event.stage === "collector") setStep(1);
      if (event.stage === "extractor" || event.stage === "verifier-a") setStep(2);
      if (event.stage === "arbiter" || event.stage === "shortlist") setStep(3);
    }
    if (event.type === "done") {
      setResult(event.result || null);
      setPipelineState((prev) => {
        const next = { ...prev };
        Object.keys(next).forEach((key) => {
          if (next[key] === "running") next[key] = "done";
        });
        return next;
      });
      if (jobType === "scan") {
        setScanResult(event.result || null);
        if (event.result && Array.isArray(event.result.bids) && event.result.bids.length === 0) {
          setMessage("No bids returned. Try broader keywords.");
          setToast({ text: "No bids returned. Try broader keywords.", kind: "warn" });
        }
        setMaxStep((prev) => Math.max(prev, 1));
        setStep(1);
      }
      if (jobType === "fetch") {
        setMaxStep((prev) => Math.max(prev, 2));
        setStep(2);
      }
      if (jobType === "evaluate") {
        setMaxStep((prev) => Math.max(prev, 3));
        setStep(3);
      }
      if (jobType === "shortlist") {
        setArbiterProgress(100);
        setArbiterStatus("Arbiter complete. Results ready.");
        setStep(3);
      }
      if (event.result?.report_json_path) {
        loadReportJson(event.result.report_json_path);
      }
      if (event.result?.out) {
        loadShortlist(event.result.out);
      }
    }
    if (event.type === "error") {
      setMessage(event.error || "Job failed.");
    }
  };

  const appendLog = (line, jobType) => {
    if (jobType === "scan") {
      setLogsScan((prev) => [...prev, line]);
    }
    if (jobType === "fetch") {
      setLogsCollect((prev) => [...prev, line]);
    }
    if (jobType === "evaluate") {
      setLogsEval((prev) => [...prev, line]);
    }
  };

  const updateLane = (bidId, updater) => {
    setLaneState((prev) => {
      const next = { ...prev };
      const lane = next[bidId] || makeLane();
      next[bidId] = updater(lane);
      return next;
    });
  };

  const addNarration = (text) => {
    setNarrative((prev) => [...prev, { text, at: new Date().toLocaleTimeString() }].slice(-8));
  };

  const appendLaneLog = (bidId, line) => {
    updateLane(bidId, (lane) => {
      const logs = [...lane.logs, line].slice(-200);
      return { ...lane, logs };
    });
  };

  const updateLaneStage = (bidId, stage, status) => {
    if (!laneStages.includes(stage)) return;
    updateLane(bidId, (lane) => ({
      ...lane,
      stages: { ...lane.stages, [stage]: status },
    }));
  };

  const updateLaneCurrent = (bidId, stage) => {
    updateLane(bidId, (lane) => ({
      ...lane,
      currentStage: stage,
    }));
  };

  const completeLaneStages = (bidId) => {
    updateLane(bidId, (lane) => {
      const nextStages = { ...lane.stages };
      Object.keys(nextStages).forEach((stage) => {
        if (nextStages[stage] === "running") {
          nextStages[stage] = "done";
        }
      });
      return { ...lane, stages: nextStages };
    });
  };

  const closeRunAllSources = () => {
    Object.values(runAllSourcesRef.current).forEach((source) => source.close());
    runAllSourcesRef.current = {};
  };

  const resetRunAll = () => {
    closeRunAllSources();
    setLaneState({});
    setLaneOrder([]);
    setRunAllMessage("");
    setRunAllActive(false);
    runAllRef.current = { pendingEvals: 0, pendingCollectors: 0 };
  };

  const runAllPipeline = async () => {
    resetRunAll();
    resetPipeline();
    setNarrative([]);
    setRemark("");
    setShortlistEmpty(false);
    setProfileData(null);
    setMessage("");
    setRunAllActive(true);
    setStep(0);
    setRunAllMessage("Launching scout...");
    setPipelineState(Object.fromEntries(stages.map((stage) => [stage.id, "idle"])));
    setPipelineState((prev) => ({ ...prev, scout: "running" }));
    addNarration("Scout Owl: Lifting off. Scanning BidPlus skies for your keywords.");
    setTimeout(() => addNarration("Mission: Scout → Collect → Verify → Arbitrate → Shortlist."), 400);
    setTimeout(() => addNarration("Parallel mode: top 3 bids will be processed side by side."), 900);
    console.info("[UI] Run full pipeline", scanForm);

    try {
      await loadProfile(selectedProfile);
      const { source } = await startJob(
        "scan",
        {
          keywords: scanForm.keywords,
          days: Number(scanForm.days),
          top: Number(scanForm.top),
          max_pages: Number(scanForm.maxPages),
          llm_filter: scanForm.llmFilter,
          force_refresh: scanForm.forceRefresh,
          llm_max_candidates: Number(scanForm.llmMaxCandidates),
          llm_batch_size: Number(scanForm.llmBatchSize),
        },
        (event) => handleRunAllScanEvent(event)
      );
      runAllSourcesRef.current.scan = source;
    } catch (error) {
      setRunAllMessage(error.message || "Failed to start scout.");
      setRunAllActive(false);
      console.error("[UI] Scout start failed", error);
    }
  };

  const handleRunAllScanEvent = (event) => {
    if (event.type === "log") {
      setLogsScan((prev) => [...prev, event.line]);
    }
    if (event.type === "done") {
      console.info("[UI] Scout done", event.result);
      setScanResult(event.result || null);
      const bids = Array.isArray(event.result?.bids) ? event.result.bids : [];
      if (bids.length === 0) {
        setRunAllMessage("No bids returned. Try broader keywords.");
        setToast({ text: "No bids returned. Try broader keywords.", kind: "warn" });
        addNarration("Scout Owl: Empty skies today. Try broader keywords.");
        setRemark("Scout Owl: Empty skies today. Let's scout again with sharper keywords.");
        closeRunAllSources();
        setRunAllActive(false);
        setPipelineState((prev) => ({ ...prev, scout: "done" }));
        return;
      }
      const selected = [...new Set(bids.map((bid) => bid.bid_id))].slice(0, 3);
      setLaneOrder(selected);
      setLaneState(
        Object.fromEntries(selected.map((bidId) => [bidId, makeLane()]))
      );
      setMaxStep((prev) => Math.max(prev, 1));
      setStep(1);
      setRunAllMessage(`Launching collectors for ${selected.length} bids...`);
      setPipelineState((prev) => ({ ...prev, scout: "done", collector: "running" }));
      addNarration(`Scout Owl: ${bids.length} matches. Dispatching top ${selected.length} for collection.`);
      runAllRef.current.pendingCollectors = selected.length;
      selected.forEach((bidId) => startCollectorForBid(bidId));
    }
    if (event.type === "error") {
      setRunAllMessage(event.error || "Scout failed.");
      addNarration("Scout Owl: Stormy skies. Scout failed.");
      closeRunAllSources();
      setRunAllActive(false);
      console.error("[UI] Scout error", event.error);
    }
  };

  const startCollectorForBid = async (bidId) => {
    try {
      updateLaneStage(bidId, "collector", "running");
      updateLaneCurrent(bidId, "collector");
      addNarration(`Collector: Docking with ${bidId}.`);
      console.info("[UI] Collector start", bidId);
      const { source } = await startJob(
        "fetch",
        { bid_id: bidId, cache_dir: fetchForm.cacheDir || null },
        (event) => handleCollectorEvent(bidId, event)
      );
      runAllSourcesRef.current[`collect-${bidId}`] = source;
    } catch (error) {
      setRunAllMessage(error.message || `Collector failed for ${bidId}.`);
      addNarration(`Collector: Docking failed for ${bidId}.`);
      updateLaneStage(bidId, "collector", "error");
      console.error("[UI] Collector start failed", bidId, error);
    }
  };

  const handleCollectorEvent = (bidId, event) => {
    if (event.type === "log") {
      appendLaneLog(bidId, event.line);
    }
    if (event.type === "stage") {
      if (event.stage !== "collector") {
        updateLaneStage(bidId, event.stage, event.status);
      }
    }
    if (event.type === "done") {
      updateLaneStage(bidId, "collector", "done");
      runAllRef.current.pendingCollectors -= 1;
      if (runAllRef.current.pendingCollectors <= 0) {
        setPipelineState((prev) => ({ ...prev, collector: "done" }));
      }
      addNarration(`Collector: Cached docs for ${bidId}.`);
      console.info("[UI] Collector done", bidId);
      startEvaluateForBid(bidId);
    }
    if (event.type === "error") {
      updateLaneStage(bidId, "collector", "error");
      appendLaneLog(bidId, event.error || "Collector failed.");
      setPipelineState((prev) => ({ ...prev, collector: "error" }));
      addNarration(`Collector: Failed on ${bidId}.`);
      console.error("[UI] Collector error", bidId, event.error);
    }
  };

  const startEvaluateForBid = async (bidId) => {
    try {
      updateLaneStage(bidId, "extractor", "running");
      updateLaneCurrent(bidId, "extractor");
      const { source } = await startJob(
        "evaluate",
        { bid_id: bidId, company_path: evalForm.companyPath },
        (event) => handleEvaluateEvent(bidId, event)
      );
      runAllSourcesRef.current[`eval-${bidId}`] = source;
      runAllRef.current.pendingEvals += 1;
      setMaxStep((prev) => Math.max(prev, 2));
      setStep(2);
      setRunAllMessage("Evaluation running across bids...");
      setPipelineState((prev) => ({
        ...prev,
        collector: prev.collector === "error" ? "error" : prev.collector,
        extractor: "running",
        "verifier-a": "running",
        "verifier-b": "running",
        "verifier-c": "running",
        arbiter: "running",
      }));
      addNarration(`Evaluator: Extracting evidence for ${bidId}.`);
      console.info("[UI] Evaluator start", bidId);
    } catch (error) {
      setRunAllMessage(error.message || `Evaluator failed for ${bidId}.`);
      addNarration(`Evaluator: Failed on ${bidId}.`);
      updateLaneStage(bidId, "extractor", "error");
      console.error("[UI] Evaluator start failed", bidId, error);
    }
  };

  const handleEvaluateEvent = (bidId, event) => {
    if (event.type === "log") {
      appendLaneLog(bidId, event.line);
    }
    if (event.type === "stage") {
      updateLaneStage(bidId, event.stage, event.status);
      updateLaneCurrent(bidId, event.stage);
    }
    if (event.type === "done") {
      completeLaneStages(bidId);
      updateLaneCurrent(bidId, "complete");
      addNarration(`Verifier quorum reached for ${bidId}.`);
      runAllRef.current.pendingEvals -= 1;
      console.info("[UI] Evaluator done", bidId);
      if (runAllRef.current.pendingEvals <= 0) {
        runAllRef.current.pendingEvals = 0;
        setRunAllMessage("All evaluations complete. Running shortlist...");
        setPipelineState((prev) => ({
          ...prev,
          extractor: "done",
          "verifier-a": "done",
          "verifier-b": "done",
          "verifier-c": "done",
          arbiter: "done",
          shortlist: "running",
        }));
        addNarration("Arbiter: Synthesizing evidence across bids.");
        startShortlist();
      }
    }
    if (event.type === "error") {
      updateLaneStage(bidId, "arbiter", "error");
      appendLaneLog(bidId, event.error || "Evaluator failed.");
      runAllRef.current.pendingEvals = Math.max(0, runAllRef.current.pendingEvals - 1);
      setPipelineState((prev) => ({ ...prev, arbiter: "error" }));
      console.error("[UI] Evaluator error", bidId, event.error);
    }
  };

  const startShortlist = async () => {
    setArbiterProgress(45);
    setArbiterStatus("Arbiter synthesizing evidence across bids...");
    setMaxStep((prev) => Math.max(prev, 3));
    setStep(3);
    try {
      const { source } = await startJob(
        "shortlist",
        { top: Number(shortlistForm.top), company_path: shortlistForm.companyPath },
        (event) => handleShortlistEvent(event)
      );
      runAllSourcesRef.current.shortlist = source;
      console.info("[UI] Shortlist start", shortlistForm);
    } catch (error) {
      setRunAllMessage(error.message || "Shortlist failed.");
      console.error("[UI] Shortlist start failed", error);
    }
  };

  const handleShortlistEvent = (event) => {
    if (event.type === "log") {
      setLogsEval((prev) => [...prev, event.line]);
    }
    if (event.type === "done") {
      setArbiterProgress(100);
      setArbiterStatus("Arbiter complete. Results ready.");
      if (event.result?.report_json_path) {
        loadReportJson(event.result.report_json_path);
      }
      if (event.result?.out) {
        loadShortlist(event.result.out);
      }
      setResult(event.result || null);
      setPipelineState((prev) => ({ ...prev, shortlist: "done" }));
      closeRunAllSources();
      setRunAllActive(false);
      setRunAllMessage("Pipeline complete. Shortlist ready.");
      if (shortlistEmpty) {
        addNarration("Scout Owl: Nothing cleared the bar. Try a sharper brief.");
        setRemark("Scout Owl: We reviewed them all, but none made the cut today.");
      } else {
        addNarration("Scout Owl: Shortlist ready. Want another pass?");
        setRemark("Scout Owl: Shortlist delivered. On to negotiations?");
      }
      console.info("[UI] Shortlist done", event.result);
    }
    if (event.type === "error") {
      setRunAllMessage(event.error || "Shortlist failed.");
      setPipelineState((prev) => ({ ...prev, shortlist: "error" }));
      closeRunAllSources();
      setRunAllActive(false);
      console.error("[UI] Shortlist error", event.error);
    }
  };

  const resetPipeline = () => {
    setPipelineState(Object.fromEntries(stages.map((stage) => [stage.id, "idle"])));
    setLogsScan([]);
    setLogsCollect([]);
    setLogsEval([]);
    setResult(null);
    setMetrics({ decision: "—", score: "—", best: "—" });
    setReportPreview("");
    setShortlistPreview("");
    setShortlistRows([]);
    setBestRow(null);
    setArbiterProgress(0);
    setArbiterStatus("Waiting for evaluation output...");
  };

  const loadReportJson = async (path) => {
    const response = await fetch(`${API_BASE}/api/files?path=${encodeURIComponent(path)}`);
    if (!response.ok) return;
    const payload = await response.json();
    setReportPreview(payload.content || "");
    try {
      const report = JSON.parse(payload.content || "{}");
      setMetrics((prev) => ({
        ...prev,
        decision: report.decision || prev.decision,
        score: report.fit_score ?? prev.score,
      }));
    } catch {
      // ignore
    }
  };

  const loadShortlist = async (path) => {
    const response = await fetch(`${API_BASE}/api/files?path=${encodeURIComponent(path)}`);
    if (!response.ok) return;
    const payload = await response.json();
    setShortlistPreview(payload.content || "");
    const parsed = parseCsv(payload.content || "");
    if (parsed.length < 2) {
      setShortlistEmpty(true);
      setShortlistRows([]);
      setBestRow(null);
      return;
    }
    setShortlistEmpty(false);
    const header = parsed[0];
    const dataRows = parsed.slice(1).map((row) => {
      const record = {};
      header.forEach((key, idx) => {
        record[key] = row[idx] ?? "";
      });
      return record;
    });
    setShortlistRows(dataRows);
    const scoreKey = header.find((key) => key === "fit_score") || "fit_score";
    const best = dataRows.reduce((acc, row) => {
      const score = parseFloat(row[scoreKey] || "-1");
      const bestScore = parseFloat(acc[scoreKey] || "-1");
      return score > bestScore ? row : acc;
    }, dataRows[0]);
    setBestRow(best);
    const bid = best.bid_id || best.bid || best.id || "—";
    const score = best[scoreKey] || "—";
    setMetrics((prev) => ({
      ...prev,
      decision: best.decision || best.recommendation || prev.decision,
      score: score || prev.score,
      best: score ? `${bid} (${score})` : bid,
    }));
  };

  const parseCsv = (text) => {
    const rows = [];
    let row = [];
    let field = "";
    let inQuotes = false;
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      const next = text[i + 1];
      if (char === "\"") {
        if (inQuotes && next === "\"") {
          field += "\"";
          i += 1;
        } else {
          inQuotes = !inQuotes;
        }
        continue;
      }
      if (char === "," && !inQuotes) {
        row.push(field);
        field = "";
        continue;
      }
      if ((char === "\n" || char === "\r") && !inQuotes) {
        if (field.length > 0 || row.length > 0) {
          row.push(field);
          rows.push(row);
          row = [];
          field = "";
        }
        continue;
      }
      field += char;
    }
    if (field.length > 0 || row.length > 0) {
      row.push(field);
      rows.push(row);
    }
    return rows.filter((r) => r.some((cell) => cell.trim() !== ""));
  };

  const handleRunScan = () => {
    runAllPipeline();
  };

  const renderCardHeader = (title, info) => (
    <div className="card-header">
      <div className="card-title">{title}</div>
      <span className="info-dot" title={info} aria-label={info}>
        i
      </span>
    </div>
  );

  const renderPipeline = (activeStages = stages, compact = false) => (
    <div className={`pipeline ${compact ? "compact" : ""}`}>
      {activeStages.map((stage) => (
        <div
          key={stage.id}
          className={`stage ${pipelineState[stage.id]}`}
        >
          <span>{stage.label}</span>
          <span className="state">{pipelineState[stage.id]}</span>
        </div>
      ))}
    </div>
  );

  const stageEmoji = (stage, status) => {
    if (status === "error") return "⛔";
    if (status === "done") return "✅";
    if (status === "running") return "⏳";
    if (stage.startsWith("verifier")) return "🔎";
    if (stage === "collector") return "📦";
    if (stage === "extractor") return "🧾";
    if (stage === "arbiter") return "⚖️";
    return "•";
  };

  const laneSummary = (lane) => {
    const running = laneStages.find((stage) => lane.stages[stage] === "running");
    const doneCount = laneStages.filter((stage) => lane.stages[stage] === "done").length;
    if (running) {
      return `${stageEmoji(running, "running")} ${running.replace("-", " ")} running`;
    }
    if (doneCount === laneStages.length) {
      return "✅ all stages complete";
    }
    if (doneCount > 0) {
      return `✅ ${doneCount} of ${laneStages.length} stages complete`;
    }
    return "⏳ queued";
  };

  const laneProgress = (lane) => {
    if (lane.stages.arbiter === "done") return 100;
    if (lane.stages.arbiter === "running") return 85;
    if (
      lane.stages["verifier-a"] === "running" ||
      lane.stages["verifier-b"] === "running" ||
      lane.stages["verifier-c"] === "running"
    ) {
      return 60;
    }
    if (lane.stages.extractor === "running") return 40;
    if (lane.stages.collector === "done") return 25;
    if (lane.stages.collector === "running") return 15;
    return 0;
  };

  const countRunning = (stage) =>
    Object.values(laneState).filter((lane) => lane.stages?.[stage] === "running").length;

  const verifierActive =
    countRunning("verifier-a") + countRunning("verifier-b") + countRunning("verifier-c");
  const scoutActive = pipelineState.scout === "running" ? 1 : 0;
  const collectorActive = countRunning("collector");
  const extractorActive = countRunning("extractor");
  const arbiterActive = pipelineState.arbiter === "running" ? 1 : 0;
  const shortlistActive = pipelineState.shortlist === "running" ? 1 : 0;

  const renderLaneGrid = () => (
    <div className="lane-grid">
      {laneOrder.map((bidId) => {
        const lane = laneState[bidId];
        if (!lane) return null;
        return (
          <div className="lane-card" key={bidId}>
            <div className="lane-header">
              <strong>{bidId}</strong>
            </div>
            <div className="lane-summary">{laneSummary(lane)}</div>
            <div className="lane-status">
              Active: {lane.currentStage === "queued" ? "queued" : lane.currentStage.replace("-", " ")}
            </div>
            <div className="lane-progress">
              <div className="lane-progress-track">
                <div className="lane-progress-fill" style={{ width: `${laneProgress(lane)}%` }}></div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );

  const canOpenStep = (id) => id <= maxStep;
  const stepState = (id) => {
    if (id < maxStep) return "done";
    if (id === step) return "active";
    return "idle";
  };
  const noBids = scanResult && Array.isArray(scanResult.bids) && scanResult.bids.length === 0;
  const showCollectActivity = activeJobType === "fetch" || logsCollect.length > 0 || laneOrder.length > 0;
  const showEvalActivity = activeJobType === "evaluate" || logsEval.length > 0 || laneOrder.length > 0;
  const showArbiter = arbiterProgress > 0 || result?.out || result?.report_json_path;
  const showPipelineInStep1 = runAllActive || laneOrder.length > 0 || scanResult;
  const pipelineProgress = (() => {
    const total = stages.length;
    const doneCount = stages.filter((stage) => pipelineState[stage.id] === "done").length;
    const runningCount = stages.filter((stage) => pipelineState[stage.id] === "running").length;
    if (doneCount === 0 && runningCount === 0) return 0;
    const progress = Math.min(100, Math.round(((doneCount + runningCount * 0.5) / total) * 100));
    return progress;
  })();
  const currentStage = stages.find((stage) => pipelineState[stage.id] === "running")?.label;

  return (
    <div className="app">
      {toast && (
        <div className={`toast ${toast.kind}`}>
          <span>{toast.text}</span>
          <button type="button" onClick={() => setToast(null)}>
            Dismiss
          </button>
        </div>
      )}
      <header className="hero">
        <div className="brand">
          <img src="/owl.svg" alt="TenderFit Owl" className="brand-logo" />
          <span className="brand-name">TenderFit Workflow Studio</span>
        </div>
        <h1>Decisions with proof, not guesses.</h1>
        <p className="subhead">
          Run the multi-agent pipeline step by step, watch each stage verify citations, and surface the best bids for your fleet profile.
        </p>
      </header>

      <main className="shell">
        <section className="panel">
          <div className="panel-head">
            <h2>Multi Agent Workflow</h2>
            {runAllMessage && <span className="panel-note">{runAllMessage}</span>}
          </div>
          <div className="stepper">
            {stepMeta.map((item) => (
              <button
                key={item.id}
                className={`step-pill ${stepState(item.id)}`}
                onClick={() => setStep(item.id)}
                type="button"
                disabled={!canOpenStep(item.id)}
              >
                <span className="step-index">Step {item.id + 1}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="agents-bar">
          <div className="card agent-overview">
            {renderCardHeader("Agents", "Overview of the agents running inside the pipeline.")}
            <div className="agent-grid">
              <div className="agent-card">
                <span className="agent-emoji">🦉</span>
                <div>
                  <strong>Scout</strong>
                  <span>Searches BidPlus and filters listings.</span>
                </div>
                <span className={`agent-count ${scoutActive ? "active" : ""}`}>{scoutActive}</span>
              </div>
              <div className="agent-card">
                <span className="agent-emoji">📦</span>
                <div>
                  <strong>Collector</strong>
                  <span>Fetches bid documents + corrigenda.</span>
                </div>
                <span className={`agent-count ${collectorActive ? "active" : ""}`}>{collectorActive}</span>
              </div>
              <div className="agent-card">
                <span className="agent-emoji">🧾</span>
                <div>
                  <strong>Extractor</strong>
                  <span>Extracts structured facts from documents.</span>
                </div>
                <span className={`agent-count ${extractorActive ? "active" : ""}`}>{extractorActive}</span>
              </div>
              <div className="agent-card">
                <span className="agent-emoji">🔎</span>
                <div>
                  <strong>Verifier</strong>
                  <span>Checks evidence and citation fidelity.</span>
                </div>
                <span className={`agent-count ${verifierActive ? "active" : ""}`}>{verifierActive}</span>
              </div>
              <div className="agent-card">
                <span className="agent-emoji">⚖️</span>
                <div>
                  <strong>Arbiter</strong>
                  <span>Resolves conflicts and scores fit.</span>
                </div>
                <span className={`agent-count ${arbiterActive ? "active" : ""}`}>{arbiterActive}</span>
              </div>
              <div className="agent-card">
                <span className="agent-emoji">🏁</span>
                <div>
                  <strong>Shortlist</strong>
                  <span>Ranks bids and prepares CSV output.</span>
                </div>
                <span className={`agent-count ${shortlistActive ? "active" : ""}`}>{shortlistActive}</span>
              </div>
            </div>
          </div>
        </section>

        <section className={`view ${step === 0 ? "active" : ""}`}>
          <div className="stack">
            {!showPipelineInStep1 ? (
              <div className="card">
                {renderCardHeader(
                  stepMeta[0].title,
                  "Configure scouting inputs and launch the full pipeline."
                )}
                <p className="helper">{stepMeta[0].helper}</p>
                <div className="row" style={{ marginTop: "12px" }}>
                  <div>
                    <label className="field-label">
                      Keywords
                      <span className="info-dot field-info" title="Search terms for BidPlus scout." aria-label="Search terms for BidPlus scout.">i</span>
                    </label>
                    <input
                      value={scanForm.keywords}
                      onChange={(e) =>
                        setScanForm((prev) => ({ ...prev, keywords: e.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <label className="field-label">
                      Days
                      <span className="info-dot field-info" title="Lookback window for closing dates." aria-label="Lookback window for closing dates.">i</span>
                    </label>
                    <input
                      type="number"
                      value={scanForm.days}
                      onChange={(e) =>
                        setScanForm((prev) => ({ ...prev, days: e.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <label className="field-label">
                      Top
                      <span className="info-dot field-info" title="Number of bids to return after filtering." aria-label="Number of bids to return after filtering.">i</span>
                    </label>
                    <input
                      type="number"
                      value={scanForm.top}
                      onChange={(e) =>
                        setScanForm((prev) => ({ ...prev, top: e.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <label className="field-label">
                      Max Pages
                      <span className="info-dot field-info" title="How many BidPlus pages to scan per keyword." aria-label="How many BidPlus pages to scan per keyword.">i</span>
                    </label>
                    <input
                      type="number"
                      value={scanForm.maxPages}
                      onChange={(e) =>
                        setScanForm((prev) => ({ ...prev, maxPages: e.target.value }))
                      }
                    />
                  </div>
                </div>
                <div className="row">
                  <div>
                    <label className="field-label">
                      LLM Filter
                      <span className="info-dot field-info" title="Use the LLM to refine matches." aria-label="Use the LLM to refine matches.">i</span>
                    </label>
                    <select
                      value={scanForm.llmFilter ? "true" : "false"}
                      onChange={(e) =>
                        setScanForm((prev) => ({
                          ...prev,
                          llmFilter: e.target.value === "true",
                        }))
                      }
                    >
                      <option value="true">On</option>
                      <option value="false">Off</option>
                    </select>
                  </div>
                  <div>
                    <label className="field-label">
                      Force Refresh
                      <span className="info-dot field-info" title="Ignore cache and re-scan BidPlus." aria-label="Ignore cache and re-scan BidPlus.">i</span>
                    </label>
                    <select
                      value={scanForm.forceRefresh ? "true" : "false"}
                      onChange={(e) =>
                        setScanForm((prev) => ({
                          ...prev,
                          forceRefresh: e.target.value === "true",
                        }))
                      }
                    >
                      <option value="false">Off</option>
                      <option value="true">On</option>
                    </select>
                  </div>
                  <div>
                    <label className="field-label">
                      LLM Max Candidates
                      <span className="info-dot field-info" title="Max bids sent to the LLM filter." aria-label="Max bids sent to the LLM filter.">i</span>
                    </label>
                    <input
                      type="number"
                      value={scanForm.llmMaxCandidates}
                      onChange={(e) =>
                        setScanForm((prev) => ({
                          ...prev,
                          llmMaxCandidates: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <label className="field-label">
                      LLM Batch Size
                      <span className="info-dot field-info" title="Batch size for LLM filtering requests." aria-label="Batch size for LLM filtering requests.">i</span>
                    </label>
                    <input
                      type="number"
                      value={scanForm.llmBatchSize}
                      onChange={(e) =>
                        setScanForm((prev) => ({
                          ...prev,
                          llmBatchSize: e.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
                <div className="row">
                  <div>
                    <label className="field-label">
                      Company Profile
                      <span className="info-dot field-info" title="Profile used for fit scoring." aria-label="Profile used for fit scoring.">i</span>
                    </label>
                    <select
                      value={selectedProfile}
                      onChange={(e) => {
                        const next = e.target.value;
                        setSelectedProfile(next);
                        setEvalForm((prev) => ({ ...prev, companyPath: next }));
                        setShortlistForm((prev) => ({ ...prev, companyPath: next }));
                        loadProfile(next);
                      }}
                    >
                      {profileOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="form-actions">
                  <button onClick={handleRunScan} type="button" disabled={runAllActive}>
                    Run Full Pipeline
                  </button>
                </div>
              </div>
            ) : (
              <div className="card">
                {renderCardHeader("Pipeline Live", "Live pipeline status and stage progress.")}
                <div className="pipeline-progress">
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${pipelineProgress}%` }}></div>
                  </div>
                  <div className="result-path">
                    {currentStage ? `Active: ${currentStage}` : "Waiting for next stage..."}
                  </div>
                </div>
                {renderPipeline(stages)}
                <div className="pipeline-hint">Top 3 bids run in parallel after scouting.</div>
              </div>
            )}

            {narrative.length > 0 && (
              <div className="card">
                {renderCardHeader(
                  "Mission Control",
                  "Narrated status updates from the demo flow."
                )}
                <div className="narrative">
                  {narrative.map((entry, index) => (
                    <div key={`${entry.at}-${index}`} className="narrative-row">
                      <span className="narrative-time">{entry.at}</span>
                      <span>{entry.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(runAllActive || laneOrder.length > 0) && (
              <div className="card">
                {renderCardHeader("Pipeline Live", "Current pipeline stage status.")}
                {renderPipeline(stages)}
              </div>
            )}

            {noBids && (
              <div className="card">
                {renderCardHeader("Scout Update", "Shown when no bids are found.")}
                <div className="empty-state">No bids returned. Try broader keywords.</div>
              </div>
            )}

            {scanResult && (
              <div className="card">
                {renderCardHeader("Scout Results", "Top bids returned from scout.")}
                {scanResult.bids && scanResult.bids.length > 0 ? (
                  <div className="result-list">
                    {scanResult.bids.map((bid) => (
                      <button
                        type="button"
                        className="result-row"
                        key={bid.bid_id}
                        onClick={() => {
                          setFetchForm((prev) => ({ ...prev, bidId: bid.bid_id }));
                          setEvalForm((prev) => ({ ...prev, bidId: bid.bid_id }));
                          setMessage(`Loaded ${bid.bid_id} into Collector/Evaluator.`);
                        }}
                      >
                        <strong>{bid.bid_id}</strong>
                        <span>{bid.title}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="notice">No bids returned yet.</div>
                )}
              </div>
            )}
          </div>
        </section>

        <section className={`view ${step === 1 ? "active" : ""}`}>
          {showCollectActivity ? (
            <div className="stack">
              <div className="card">
                {renderCardHeader(
                  "Bid Lanes",
                  "Per-bid progress for collector and evaluator stages."
                )}
                {laneOrder.length > 0 ? renderLaneGrid() : renderPipeline(stages.filter((stage) => stage.id !== "scout"))}
              </div>
            </div>
          ) : (
            <div className="empty-state">
              Queue a bid to see the collector pipeline and per-bid logs.
            </div>
          )}
        </section>

        <section className={`view ${step === 2 ? "active" : ""}`}>
          {showEvalActivity ? (
            <div className="stack">
              <div className="card">
                {renderCardHeader(
                  "Bid Lanes",
                  "Per-bid progress for collector and evaluator stages."
                )}
                {laneOrder.length > 0 ? renderLaneGrid() : renderPipeline(stages.filter((stage) => stage.id !== "scout"))}
              </div>
            </div>
          ) : (
            <div className="empty-state">
              Launch an evaluation run to watch extractor, verifiers, and arbiter in real time.
            </div>
          )}
        </section>

        <section className={`view ${step === 3 ? "active" : ""}`}>
          {showArbiter ? (
            <div className="stack">
              <div className="card">
                {renderCardHeader(
                  "Company Profile",
                  "Profile used to score and shortlist bids."
                )}
                <div className="profile-summary">
                  <div className="profile-pill">
                    {profileOptions.find((opt) => opt.value === selectedProfile)?.label || "Profile"}
                  </div>
                  {profileData ? (
                    <div className="profile-details">
                      <details open>
                        <summary>Fleet</summary>
                        <div className="profile-grid">
                          <span>Sedan</span><span>{profileData.fleet?.sedan ?? "—"}</span>
                          <span>SUV</span><span>{profileData.fleet?.suv ?? "—"}</span>
                          <span>MUV</span><span>{profileData.fleet?.muv ?? "—"}</span>
                          <span>Hatchback</span><span>{profileData.fleet?.hatchback ?? "—"}</span>
                          <span>Model Year Min</span><span>{profileData.fleet?.model_year_min ?? "—"}</span>
                        </div>
                      </details>
                      <details>
                        <summary>Documents</summary>
                        <div className="profile-grid">
                          <span>GST</span><span>{profileData.docs?.gst ? "Yes" : "No"}</span>
                          <span>PAN</span><span>{profileData.docs?.pan ? "Yes" : "No"}</span>
                          <span>Permits</span><span>{profileData.docs?.permits ? "Yes" : "No"}</span>
                          <span>Insurance</span><span>{profileData.docs?.insurance ? "Yes" : "No"}</span>
                        </div>
                      </details>
                      <details>
                        <summary>Financials</summary>
                        <div className="profile-grid">
                          <span>Turnover (3y)</span>
                          <span>{(profileData.financials?.turnover_last_3y_inr || []).join(", ") || "—"}</span>
                        </div>
                      </details>
                      <details>
                        <summary>Experience</summary>
                        <div className="profile-grid">
                          <span>Govt Contracts</span><span>{profileData.experience?.govt_contracts_count ?? "—"}</span>
                          <span>Similar Work (yrs)</span><span>{profileData.experience?.similar_work_years ?? "—"}</span>
                        </div>
                      </details>
                      <details>
                        <summary>Operations</summary>
                        <div className="profile-grid">
                          <span>Cities</span><span>{(profileData.operations?.cities_served || []).join(", ") || "—"}</span>
                          <span>Drivers</span><span>{profileData.operations?.drivers_available ?? "—"}</span>
                          <span>24x7</span><span>{profileData.operations?.["24x7_capable"] ? "Yes" : "No"}</span>
                        </div>
                      </details>
                    </div>
                  ) : (
                    <div className="profile-path">Profile details unavailable.</div>
                  )}
                </div>
              </div>
              <div className="card">
                {renderCardHeader(
                  "Insights",
                  "Best bid metrics and shortlist summary."
                )}
                <div className="insights">
                  <div className="metric">
                    <div className="metric-label">Decision</div>
                    <div className="metric-value">{metrics.decision}</div>
                  </div>
                  <div className="metric">
                    <div className="metric-label">Fit Score</div>
                    <div className="metric-value">{metrics.score}</div>
                  </div>
                  <div className="metric">
                    <div className="metric-label">Best Bid</div>
                    <div className="metric-value">{metrics.best}</div>
                  </div>
                </div>
                <div className="best-bid">
                  <span>Best match</span>
                  <strong>{metrics.best}</strong>
                </div>
                {shortlistRows.length > 0 && (
                  <div className="shortlist-accordion">
                    <div className="table-title">Shortlist (Top {shortlistRows.length})</div>
                    {shortlistRows.map((row, idx) => (
                      <details
                        key={`${row.bid_id || idx}`}
                        className="accordion-item"
                        open={idx === 0}
                      >
                        <summary>
                          <span className="summary-left">
                            <span className="chevron">⌄</span>
                            <span>{row.bid_id || row.bid || "—"}</span>
                          </span>
                          {(() => {
                            const decision = (row.decision || row.recommendation || "—").toUpperCase();
                            const decisionClass = decision === "GO" ? "go" : "no-go";
                            return (
                              <>
                                <span className={`pill score ${decisionClass}`}>{row.fit_score || "—"}</span>
                                <span className={`pill decision ${decisionClass}`}>
                                  {decision === "GO" ? "✅ GO" : "❌ NO_GO"}
                                </span>
                              </>
                            );
                          })()}
                        </summary>
                        <div className="accordion-body">
                          <div className="accordion-label">Summary</div>
                          <p>{row.summary || row.notes || "—"}</p>
                        </div>
                      </details>
                    ))}
                  </div>
                )}
                {result?.out && (
                  <a
                    className="download-link"
                    href={`${API_BASE}/api/files?path=${encodeURIComponent(result.out)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Download shortlist CSV
                  </a>
                )}
              </div>
              <div className="card mascot-card">
                {renderCardHeader("Scout Owl", "Mascot commentary and closing remark.")}
                <pre className="mascot-art">
{`  /\\_/\\\\\n ( o.o )\n  > ^ <`}
                </pre>
                <div className="mascot-remark">
                  {remark || "Scout Owl: Standing by for your next mission."}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              Run the shortlist to see arbiter progress, final rankings, and insights.
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>Made with ❤️ by Priyank Mehta for AI Engineers Day Hackathon</span>
        <span className="footer-sep">•</span>
        <span>Presented by OpenAI</span>
        <span className="footer-sep">•</span>
        <span>Peak XV</span>
        <span className="footer-sep">•</span>
        <span>Activate</span>
      </footer>
    </div>
  );
}
