"""Interactive demo flow for TenderFit CLI."""

from __future__ import annotations

import json
import os
import threading
import concurrent.futures
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


OWL_ART = r"""
  /\_/\ 
 ( o.o )
  > ^ <
"""

_progress_lock = threading.Lock()
_progress_thread: threading.Thread | None = None
_progress_stop: threading.Event | None = None
_progress_stage: str | None = None
_parallel_mode = False
_thread_context = threading.local()
_progress_marks: dict[tuple[str, str], int] = {}
_dashboard: "ProgressDashboard | None" = None


def _say(message: str) -> None:
    print(f"Scout Owl: {message}")


def _run_command(command: list[str]) -> dict[str, Any] | None:
    print("\n$ " + " ".join(command))
    last_json: dict[str, Any] | None = None
    buffer: list[str] = []
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for raw in process.stdout:
        line = raw.rstrip()
        if not line:
            continue
        buffer.append(line)
        _print_human_log(line)
        if line.lstrip().startswith("{") or line.lstrip().startswith("["):
            try:
                last_json = json.loads(line)
            except json.JSONDecodeError:
                pass
    process.wait()
    if process.returncode != 0:
        _stop_progress(final=True)
        raise RuntimeError(f"Command failed: {' '.join(command)}")
    _stop_progress(final=True)
    if last_json is None:
        joined = "\n".join(buffer)
        last_json = _extract_json_from_text(joined)
    return last_json


def _print_human_log(line: str) -> None:
    bid_id = _extract_bid_id(line) or _get_current_bid_id()
    if "collector.start" in line:
        doc_count = _extract_count(line, "doc_count")
        _stage_banner(
            "Collector",
            "Gathering evidence packs, PDFs, and attachments. Tagging doc types.",
            icon="(📦)",
            bid_id=bid_id,
        )
        duration = _estimate_duration(doc_count, base=2.5, minimum=2.0, maximum=10.0)
        _start_progress("Collector", duration, bid_id)
        return
    if "extractor.start" in line:
        chunk_count = _extract_count(line, "chunk_count")
        _stage_banner(
            "Extractor",
            "Reading PDFs, chunking pages, and anchoring quotes to page numbers.",
            icon="(📄)",
            bid_id=bid_id,
        )
        duration = _estimate_duration(chunk_count, base=0.2, minimum=4.0, maximum=25.0)
        _start_progress("Extractor", duration, bid_id)
        return
    if "verifier.start" in line:
        req_count = _requirements_count(bid_id)
        if "verifier_id=A" in line:
            _stage_banner(
                "Verifier A",
                "Checks every requirement has a citation and the quote is present.",
                icon="(🔍)",
                bid_id=bid_id,
            )
            duration = _estimate_duration(req_count, base=0.6, minimum=8.0, maximum=30.0)
            _start_progress("Verifier A", duration, bid_id)
            return
        if "verifier_id=B" in line:
            _stage_banner(
                "Verifier B",
                "Cross-checks clauses for contradictions and missing constraints.",
                icon="(🧪)",
                bid_id=bid_id,
            )
            duration = _estimate_duration(req_count, base=0.6, minimum=8.0, maximum=30.0)
            _start_progress("Verifier B", duration, bid_id)
            return
        if "verifier_id=C" in line:
            _stage_banner(
                "Verifier C",
                "Validates corrigendum precedence and flags conflicts.",
                icon="(⚖️)",
                bid_id=bid_id,
            )
            duration = _estimate_duration(req_count, base=0.6, minimum=8.0, maximum=30.0)
            _start_progress("Verifier C", duration, bid_id)
            return
    if "arbiter.start" in line:
        if _parallel_mode:
            return
        _stage_banner(
            "Arbiter",
            "Merges verifier votes, computes FitScore, and drafts the memo.",
            icon="(🧭)",
            bid_id=bid_id,
        )
        req_count = _requirements_count(bid_id)
        duration = _estimate_duration(req_count, base=0.4, minimum=6.0, maximum=20.0)
        _start_progress("Arbiter", duration, bid_id)
        return
    if line.startswith("{") or line.startswith("["):
        return
    print("  " + line)


def _stage_banner(name: str, detail: str, icon: str, bid_id: str | None) -> None:
    bar = "█" * 16
    suffix = f" [{bid_id}]" if bid_id else ""
    if _parallel_mode and sys.stdout.isatty():
        _ensure_dashboard().add_event(f"{icon} {name}{suffix} — {detail}")
        return
    print(f"\n{icon} {name}{suffix}")
    print(f"[{bar:16}] ⟶ {detail}\n")


def _start_progress(stage: str, duration: float | None, bid_id: str | None) -> None:
    if _parallel_mode:
        stop_event = threading.Event()
        thread = threading.Thread(
            target=_progress_worker,
            args=(stage, stop_event, duration, bid_id),
            daemon=True,
        )
        thread.start()
        return
    _stop_progress(final=False)
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_progress_worker,
        args=(stage, stop_event, duration, bid_id),
        daemon=True,
    )
    with _progress_lock:
        global _progress_thread, _progress_stop, _progress_stage
        _progress_thread = thread
        _progress_stop = stop_event
        _progress_stage = stage
    thread.start()


def _stop_progress(final: bool) -> None:
    if _parallel_mode:
        return
    with _progress_lock:
        global _progress_thread, _progress_stop, _progress_stage
        stop_event = _progress_stop
        stage = _progress_stage
        _progress_stop = None
        _progress_stage = None
    if stop_event:
        stop_event.set()
    if final and stage:
        _render_progress(stage, 100, None)
        print()


def _progress_worker(
    stage: str,
    stop_event: threading.Event,
    duration: float | None,
    bid_id: str | None,
) -> None:
    duration = duration or 8.0
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        ratio = min(elapsed / max(duration, 0.1), 1.0)
        percent = int(ratio * 95)
        _render_progress(stage, percent, bid_id)
        if percent >= 95:
            break
        time.sleep(0.3)
    if not stop_event.is_set():
        _render_progress(stage, 95, bid_id)


def _render_progress(stage: str, percent: int, bid_id: str | None) -> None:
    if _parallel_mode:
        if not bid_id:
            if sys.stdout.isatty():
                _ensure_dashboard().update_global_stage(stage, percent)
            return
        key = (bid_id, stage)
        with _progress_lock:
            last = _progress_marks.get(key, -5)
            if percent - last < 5 and percent != 95 and percent != 100:
                return
            _progress_marks[key] = percent
        if sys.stdout.isatty():
            _ensure_dashboard().update_bid_stage(bid_id, stage, percent)
        else:
            bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
            line = f"[{bid_id}] {stage:10} [{bar}] {percent:3d}%"
            print("  " + line)
        return
    blocks = int(percent / 5)
    bar = "█" * blocks + "░" * (20 - blocks)
    print(f"\r  {stage:10} [{bar}] {percent:3d}%", end="", flush=True)


class ProgressDashboard:
    def __init__(self) -> None:
        self.lines: dict[str, str] = {}
        self.bid_progress: dict[str, dict[str, int]] = {}
        self.events: list[str] = []
        self.last_render = 0.0

    def set_bids(self, bid_ids: list[str]) -> None:
        for bid_id in bid_ids:
            self.bid_progress.setdefault(
                bid_id,
                {
                    "scout": 0,
                    "collector": 0,
                    "extractor": 0,
                    "verifier": 0,
                    "arbiter": 0,
                },
            )
        self._render()

    def update_bid_stage(self, bid_id: str, stage: str, percent: int) -> None:
        if bid_id not in self.bid_progress:
            self.set_bids([bid_id])
        normalized = _normalize_stage(stage)
        if normalized == "verifier":
            current = self.bid_progress[bid_id].get("verifier", 0)
            self.bid_progress[bid_id]["verifier"] = max(current, percent)
        else:
            self.bid_progress[bid_id][normalized] = max(
                self.bid_progress[bid_id].get(normalized, 0), percent
            )
        self._render()

    def update_global_stage(self, stage: str, percent: int) -> None:
        for bid_id in self.bid_progress.keys():
            self.update_bid_stage(bid_id, stage, percent)

    def update_line(self, key: str, line: str) -> None:
        self.lines[key] = line
        self._render()

    def add_event(self, message: str) -> None:
        self.events.append(message)
        self.events = self.events[-6:]
        self._render()

    def _render(self) -> None:
        now = time.time()
        if now - self.last_render < 0.1:
            return
        self.last_render = now
        header = "TenderFit Demo — Parallel Progress"
        body = [header, "-" * len(header)]
        body.extend(self.events)
        if self.events:
            body.append("")
        if self.bid_progress:
            body.append("Bid Progress (S=Scout, C=Collector, E=Extractor, V=Verifier, A=Arbiter)")
            body.append("Legend: 🧭 Scout  📦 Collector  📄 Extractor  🔍 Verifier  🧠 Arbiter")
            for bid_id in sorted(self.bid_progress.keys()):
                progress = self.bid_progress[bid_id]
                row = _render_bid_row(bid_id, progress)
                body.append(row)
        else:
            for key in sorted(self.lines.keys()):
                body.append(self.lines[key])
        output = "\n".join(body)
        sys.stdout.write("\x1b[2J\x1b[H" + output + "\n")
        sys.stdout.flush()


def _ensure_dashboard() -> ProgressDashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = ProgressDashboard()
    return _dashboard


def _normalize_stage(stage: str) -> str:
    stage_lower = stage.lower()
    if "collector" in stage_lower:
        return "collector"
    if "extractor" in stage_lower:
        return "extractor"
    if "verifier" in stage_lower:
        return "verifier"
    if "arbiter" in stage_lower:
        return "arbiter"
    if "scout" in stage_lower:
        return "scout"
    return stage_lower


def _mini_bar(percent: int, width: int) -> str:
    filled = int(round((percent / 100) * width))
    return "█" * filled + "░" * (width - filled)


def _render_bid_row(bid_id: str, progress: dict[str, int]) -> str:
    scout = _mini_bar(progress.get("scout", 0), 6)
    collector = _mini_bar(progress.get("collector", 0), 6)
    extractor = _mini_bar(progress.get("extractor", 0), 6)
    verifier = _mini_bar(progress.get("verifier", 0), 6)
    arbiter = _mini_bar(progress.get("arbiter", 0), 20)
    return (
        f"{bid_id}  🧭S[{scout}] 📦C[{collector}] 📄E[{extractor}] "
        f"🔍V[{verifier}]  🧠A[{arbiter}] {progress.get('arbiter', 0):3d}%"
    )


def _extract_count(line: str, key: str) -> int | None:
    match = re.search(rf"{key}=(\\d+)", line)
    if not match:
        return None
    return int(match.group(1))


def _estimate_duration(value: int | None, base: float, minimum: float, maximum: float) -> float:
    if value is None:
        return minimum
    duration = value * base
    return max(minimum, min(duration, maximum))


def _requirements_count(bid_id: str | None) -> int | None:
    if not bid_id:
        return None
    path = Path("artifacts") / bid_id / "tender_requirements.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    requirements = data.get("requirements", [])
    if isinstance(requirements, list):
        return len(requirements)
    return None


def _unique_bids(scan_output: dict[str, Any]) -> list[dict[str, Any]]:
    bids = scan_output.get("bids", [])
    if not bids:
        return []
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for bid in bids:
        bid_id = bid.get("bid_id")
        if not bid_id or bid_id in seen:
            continue
        seen.add(bid_id)
        unique.append(bid)
    return unique


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    for start in range(len(text) - 1, -1, -1):
        if text[start] not in "[{":
            continue
        snippet = text[start:]
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _select_company_profile() -> str:
    candidates = sorted(Path("examples").glob("*.json"))
    if not candidates:
        raise RuntimeError("No company profiles found under examples/.")

    print("\nCompany profiles:")
    options: list[tuple[str, str]] = []
    for idx, path in enumerate(candidates, start=1):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("company_name") or path.name
        except json.JSONDecodeError:
            name = path.name
        options.append((str(path), str(name)))
        print(f"  [{idx}] {name} — {path}")

    while True:
        choice = input("Select a company profile number: ").strip()
        if not choice.isdigit():
            print("Please enter a number.")
            continue
        index = int(choice)
        if 1 <= index <= len(options):
            return options[index - 1][0]
        print("Choice out of range.")


def _best_bid_from_csv(csv_path: str) -> str | None:
    path = Path(csv_path)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(content) < 2:
        return None
    header = content[0].split(",")
    rows = [row.split(",") for row in content[1:] if row.strip()]
    if not rows:
        return None
    try:
        bid_idx = header.index("bid_id")
    except ValueError:
        bid_idx = 0
    try:
        score_idx = header.index("fit_score")
    except ValueError:
        score_idx = None
    best = rows[0]
    if score_idx is not None:
        def score(row: list[str]) -> float:
            try:
                return float(row[score_idx])
            except (ValueError, IndexError):
                return -1.0
        best = max(rows, key=score)
    bid_id = best[bid_idx] if bid_idx < len(best) else None
    score_value = None
    if score_idx is not None and score_idx < len(best):
        score_value = best[score_idx]
    if bid_id and score_value is not None:
        return f"{bid_id} (FitScore {score_value})"
    return bid_id


def _extract_bid_id(line: str) -> str | None:
    match = re.search(r"bid_id=([A-Z0-9/._-]+)", line)
    if not match:
        return None
    return match.group(1)


def _set_current_bid_id(bid_id: str) -> None:
    _thread_context.bid_id = bid_id


def _get_current_bid_id() -> str | None:
    return getattr(_thread_context, "bid_id", None)


def _process_bid(bid_id: str, company: str) -> None:
    _set_current_bid_id(bid_id)
    _say(f"Processing bid {bid_id}.")

    artifacts_dir = Path("artifacts") / bid_id
    _say("Step 2: Fetching documents.")
    _run_command(
        [
            sys.executable,
            "-m",
            "tenderfit.cli",
            "fetch",
            "--bid-id",
            bid_id,
            "--out",
            str(artifacts_dir),
            "--cache-dir",
            "/tmp/tenderfit_collect_cache_demo",
        ]
    )

    _say("Step 3: Evaluating fit with citations.")
    _say("Extractor is parsing documents. Verifiers will run in parallel.")
    _say("Waiting on OpenAI responses for verifiers and arbiter. This can take a moment.")
    report_path = Path("reports") / f"{bid_id.replace('/', '-')}.md"
    _run_command(
        [
            sys.executable,
            "-m",
            "tenderfit.cli",
            "evaluate",
            "--bid-id",
            bid_id,
            "--company",
            company,
            "--out",
            str(report_path),
        ]
    )


def run_demo() -> None:
    print(OWL_ART)
    _say("Welcome to the TenderFit demo. I will guide the full run.")

    keywords = input("Enter keywords (e.g., 'cabs taxi'): ").strip()
    if not keywords:
        keywords = "cabs taxi"
        _say(f"Using default keywords: {keywords}")

    company = _select_company_profile()

    _say("Step 1: Scouting for matching bids.")
    _say("Scanning BidPlus listings and applying keyword + LLM filters. This can take a bit.")
    _start_progress("Scout", 10.0, None)
    use_llm_filter = bool(os.environ.get("OPENAI_API_KEY"))
    if not use_llm_filter:
        _say("No OPENAI_API_KEY found. Running scan without LLM filtering.")
    scan_output = _run_command(
        [
            sys.executable,
            "-m",
            "tenderfit.cli",
            "scan",
            "--keywords",
            keywords,
            "--days",
            "2",
            "--top",
            "5",
            "--max-pages",
            "2",
            "--force-refresh",
        ]
        + (
            [
                "--llm-filter",
                "--llm-max-candidates",
                "5",
                "--llm-batch-size",
                "5",
            ]
            if use_llm_filter
            else []
        )
    )
    if scan_output is None:
        raise RuntimeError("Scan did not return JSON output.")
    _stop_progress(final=True)

    bids = _unique_bids(scan_output)
    if not bids:
        _say("No bids returned from scan. Try broader keywords or increase max pages.")
        notes = scan_output.get("notes") if isinstance(scan_output, dict) else None
        if notes:
            print(f"  Notes: {notes}")
        print(OWL_ART)
        _say("Empty skies today. Let's scout again with sharper keywords.")
        return
    bids = bids[:3]
    print("\nTop bids (processing top 3 in parallel):")
    for idx, bid in enumerate(bids, start=1):
        title = bid.get("title", "")
        print(f"  [{idx}] {bid.get('bid_id')} — {title[:80]}")

    global _parallel_mode
    _parallel_mode = True
    if sys.stdout.isatty():
        dashboard = _ensure_dashboard()
        dashboard.set_bids([bid["bid_id"] for bid in bids])
        for bid in bids:
            dashboard.update_bid_stage(bid["bid_id"], "scout", 100)
    _say("Parallel mode enabled. Processing bids concurrently.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(_process_bid, bid["bid_id"], company)
            for bid in bids
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    arbiter_stop = None
    if sys.stdout.isatty():
        dashboard = _ensure_dashboard()
        dashboard.add_event("🧠 Arbiter — global synthesis and decision roll-up")
        arbiter_stop = threading.Event()
        arbiter_thread = threading.Thread(
            target=_progress_worker,
            args=("Arbiter", arbiter_stop, 12.0, None),
            daemon=True,
        )
        arbiter_thread.start()
    _parallel_mode = False

    _say("Step 4: Shortlisting top bids.")
    shortlist_output = _run_command(
        [
            sys.executable,
            "-m",
            "tenderfit.cli",
            "shortlist",
            "--company",
            company,
            "--top",
            "5",
            "--bid-ids",
            ",".join([bid["bid_id"] for bid in bids]),
            "--out",
            "shortlists/shortlist.csv",
        ]
    )
    if sys.stdout.isatty():
        if arbiter_stop:
            arbiter_stop.set()
            _render_progress("Arbiter", 100, None)
        for bid in bids:
            _ensure_dashboard().update_bid_stage(bid["bid_id"], "arbiter", 100)

    _say("Demo complete. Reports and shortlist are ready.")
    if isinstance(shortlist_output, dict):
        out_path = shortlist_output.get("out")
        count = shortlist_output.get("count")
        print("\nFinal Summary")
        print(f"  Processed bids: {len(bids)}")
        if count is not None:
            print(f"  Shortlisted: {count}")
        if out_path:
            print(f"  CSV: {out_path}")
            best = _best_bid_from_csv(out_path)
            if best:
                print(f"  Best match: {best}")
        print(OWL_ART)
        if count == 0:
            _say("No winners today. Better to skip a bid than wing it.")
        else:
            _say("Shortlist locked. Hoot hoot — on to the winning bids.")
    time.sleep(0.2)
