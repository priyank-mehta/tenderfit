"""CLI entrypoints for TenderFit."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tenderfit")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="Scan tender listings")
    scan.add_argument("--keywords", required=True)
    scan.add_argument("--days", type=int, default=14)
    scan.add_argument("--top", type=int, default=30)
    scan.add_argument("--data", help="Path to cached bids.json or bids.jsonl")
    scan.add_argument("--cache-dir", help="Tool cache directory")
    scan.add_argument("--max-pages", type=int, default=5)
    scan.add_argument("--no-server-search", action="store_true")
    scan.add_argument("--out", help="Write matched bids to a JSON file")
    scan.add_argument("--llm-filter", action="store_true")
    scan.add_argument("--llm-model", default="gpt-4.1-mini")
    scan.add_argument("--llm-max-candidates", type=int, default=100)
    scan.add_argument("--llm-batch-size", type=int, default=5)
    scan.add_argument("--force-refresh", action="store_true")

    fetch = subparsers.add_parser("fetch", help="Fetch bid documents")
    fetch.add_argument("--bid-id", required=True)
    fetch.add_argument("--out", required=True)
    fetch.add_argument("--cache-dir")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate bid fit")
    evaluate.add_argument("--bid-id", required=True)
    evaluate.add_argument("--company", required=True)
    evaluate.add_argument("--out", required=True)

    shortlist = subparsers.add_parser("shortlist", help="Rank top bids")
    shortlist.add_argument("--company", required=True)
    shortlist.add_argument("--top", type=int, default=10)
    shortlist.add_argument("--out", required=True)
    shortlist.add_argument("--bid-ids", help="Comma-separated bid IDs to include")

    eval_cmd = subparsers.add_parser("eval", help="Run eval suites")
    eval_cmd.add_argument("--suite", default="quick")
    eval_cmd.add_argument("--min-coverage", type=float, default=0.9)

    demo = subparsers.add_parser("demo", help="Interactive demo flow")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "eval":
        from tenderfit.evals import run_cli

        raise SystemExit(run_cli(args.suite, min_coverage=args.min_coverage))

    if args.command == "demo":
        from tenderfit.demo import run_demo

        run_demo()
        return

    if args.command == "scan":
        listing_written = 0
        if args.data:
            from tenderfit.tools.search_bids import search_bids

            data_path = Path(args.data)
            output = search_bids(
                keyword=args.keywords,
                days=args.days,
                top_n=args.top,
                data_path=str(data_path),
                cache_dir=args.cache_dir,
            )

            bids = []
            for bid in output.bids:
                item = {
                    "bid_id": bid.bid_id,
                    "title": bid.title,
                    "links": [bid.url] if bid.url else [],
                }
                if bid.summary:
                    item["summary"] = bid.summary
                listing_dir = Path("artifacts") / bid.bid_id
                listing_dir.mkdir(parents=True, exist_ok=True)
                listing_path = listing_dir / "listing.json"
                listing_payload = {
                    "query": args.keywords,
                    "bid": {
                        "bid_id": bid.bid_id,
                        "title": bid.title,
                        "url": bid.url,
                        "closing_date": bid.published_at,
                        "summary": bid.summary,
                    },
                }
                listing_path.write_text(
                    json.dumps(listing_payload, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                listing_written += 1
                bids.append(item)

            notes_parts = [
                f"matched {len(bids)} of {output.total}",
                f"cached={output.cached}",
            ]
            if not data_path.exists():
                notes_parts.append(f"missing data file: {data_path}")
            notes_parts.append(f"listing_written={listing_written}")
        else:
            from tenderfit.tools.bidplus_scout import bidplus_scout

            output = bidplus_scout(
                keywords=args.keywords,
                days=args.days,
                top_n=args.top,
                max_pages=args.max_pages,
                cache_dir=args.cache_dir,
                use_server_search=not args.no_server_search,
                write_data_path=args.out,
                llm_filter=args.llm_filter,
                llm_model=args.llm_model,
                llm_max_candidates=args.llm_max_candidates,
                llm_batch_size=args.llm_batch_size,
                force_refresh=args.force_refresh,
            )

            bids = []
            for bid in output.bids:
                item = {
                    "bid_id": bid.bid_id,
                    "title": bid.title,
                    "links": [bid.url] if bid.url else [],
                }
                if bid.closing_date:
                    item["closing_date"] = bid.closing_date.split("T")[0]
                if bid.summary:
                    item["summary"] = bid.summary
                listing_dir = Path("artifacts") / bid.bid_id
                listing_dir.mkdir(parents=True, exist_ok=True)
                listing_path = listing_dir / "listing.json"
                listing_payload = {
                    "query": args.keywords,
                    "bid": {
                        "bid_id": bid.bid_id,
                        "title": bid.title,
                        "url": bid.url,
                        "closing_date": bid.closing_date,
                        "summary": bid.summary,
                        "raw": bid.raw,
                    },
                }
                listing_path.write_text(
                    json.dumps(listing_payload, ensure_ascii=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                listing_written += 1
                bids.append(item)

            notes_parts = [
                f"matched {len(bids)} of {output.total}",
                f"cached={output.cached}",
            ]
            if output.notes:
                notes_parts.append(output.notes)
            notes_parts.append(f"listing_written={listing_written}")

        payload = {
            "query": args.keywords,
            "bids": bids,
            "notes": "; ".join(notes_parts),
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    if args.command == "fetch":
        from tenderfit.tools.bidplus_collect_docs import collect_docs

        bid_id = args.bid_id
        out_dir = Path(args.out)
        listing_path = out_dir / "listing.json"
        if not listing_path.exists():
            listing_path = Path("artifacts") / bid_id / "listing.json"
        output = collect_docs(
            bid_id=bid_id,
            listing_path=str(listing_path),
            out_dir=str(out_dir),
            cache_dir=args.cache_dir,
        )

        manifest = {
            "bid_id": bid_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "documents": [doc.model_dump() for doc in output.documents],
        }
        manifest_path = out_dir / "evidence_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        payload = {
            "bid_id": bid_id,
            "documents": [doc.model_dump() for doc in output.documents],
            "errors": output.errors,
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    if args.command == "evaluate":
        from tenderfit.app import evaluate_bid

        bid_id = args.bid_id
        out_path = Path(args.out)
        artifacts_dir = Path("artifacts") / bid_id
        manifest_path = artifacts_dir / "evidence_manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"Missing evidence manifest: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc_urls = [
            f"file://{doc['local_path']}"
            for doc in manifest.get("documents", [])
            if doc.get("local_path")
        ]
        if not doc_urls:
            raise SystemExit("No document URLs found in evidence manifest.")

        report, report_md = evaluate_bid(
            bid_id=bid_id,
            doc_urls=doc_urls,
            company_profile_path=args.company,
            artifacts_dir=str(artifacts_dir),
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")

        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / f"{bid_id}.json"
        json_path.write_text(
            json.dumps(report, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

        payload = {
            "bid_id": bid_id,
            "report_path": str(out_path),
            "report_json_path": str(json_path),
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    if args.command == "shortlist":
        reports_dir = Path("reports")
        report_files = list(reports_dir.rglob("*.json"))
        if not report_files:
            raise SystemExit("No report JSON files found under reports/.")

        allowed_ids = None
        if args.bid_ids:
            allowed_ids = {bid.strip() for bid in args.bid_ids.split(",") if bid.strip()}

        rows = []
        for path in report_files:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            bid_id = report.get("bid_id")
            if allowed_ids is not None and bid_id not in allowed_ids:
                continue
            decision = report.get("decision")
            fit_score = report.get("fit_score")
            summary = report.get("summary")
            if bid_id is None or fit_score is None:
                continue
            rows.append(
                {
                    "bid_id": bid_id,
                    "decision": decision,
                    "fit_score": fit_score,
                    "summary": summary,
                    "report_json_path": str(path),
                }
            )

        rows.sort(key=lambda row: row.get("fit_score", 0), reverse=True)
        selected = rows[: args.top]

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["bid_id", "decision", "fit_score", "summary", "report_json_path"],
            )
            writer.writeheader()
            for row in selected:
                writer.writerow(row)

        payload = {
            "count": len(selected),
            "out": str(out_path),
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    raise SystemExit("Command not implemented yet.")


if __name__ == "__main__":
    main()
