"""Load a verified document corpus and run native Snowflake agents using named profiles."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from snowflake.connector.errors import Error

from .agent import ask, deploy, evaluate, verify_runtime, verify_search
from .cloud import ingest, setup, verify_corpus
from .config import literal, load_config
from .db import Database
from .extraction import extract_pdfs
from .source import download, read_manifest, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".config" / "snow-analytical-search" / "demo.toml",
        help="Configuration file (default: ~/.config/snow-analytical-search/demo.toml)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in (
        "preflight",
        "check-ai",
        "download",
        "extract-pdfs",
        "setup",
        "ingest",
        "deploy",
        "evaluate",
        "verify-runtime",
        "pause",
        "resume",
    ):
        commands.add_parser(name)
    question_parser = commands.add_parser("ask")
    question_parser.add_argument("question")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--corpus-only", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == "preflight":
            with Database(config, "ACCOUNTADMIN", bootstrap=True) as db:
                result = {
                    "identity": db.identity,
                    "cross_region": db.run(
                        "SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT"
                    ),
                }
        elif args.command == "download":
            result = {"files": download(config)}
        elif args.command == "extract-pdfs":
            result = extract_pdfs(config)
        elif args.command == "setup":
            result = setup(config)
        elif args.command == "check-ai":
            result = {}
            with Database(config, config.runner) as db:
                for name, sql in (
                    ("ai_filter", "SELECT AI_FILTER('This text describes mental health support.')"),
                    (
                        "ai_complete",
                        "SELECT AI_COMPLETE('claude-haiku-4-5', 'Reply with only OK.')",
                    ),
                ):
                    try:
                        result[name] = {"result": db.scalar(sql), "query_id": db.query_id}
                    except Error as exc:
                        result[name] = {"error": str(exc), "query_id": exc.sfqid}
            write_json(config.state_dir / "capability-probes.json", result)
            if any("error" in item for item in result.values()):
                print(json.dumps(result, indent=2))
                raise ValueError("AI prerequisites failed; see capability-probes.json")
        elif args.command == "ingest":
            result = ingest(config)
        elif args.command == "deploy":
            result = deploy(config)
        elif args.command == "ask":
            result = ask(config, args.question)
        elif args.command == "evaluate":
            result = evaluate(config)
        elif args.command == "verify-runtime":
            result = verify_runtime(config)
        elif args.command == "verify":
            entries = read_manifest(config)
            with Database(config, config.owner) as db:
                result = verify_corpus(db, config, entries)
            result["scope"] = "corpus_only" if args.corpus_only else "corpus_and_search"
            if not args.corpus_only:
                with Database(config, config.runner) as db:
                    result["search_evidence"] = verify_search(db, config, entries)
            name = "corpus-verification.json" if args.corpus_only else "verification.json"
            write_json(config.state_dir / name, result)
        else:
            operation = "SUSPEND" if args.command == "pause" else "RESUME"
            with Database(config, config.owner) as db:
                services = db.run(f"SHOW CORTEX SEARCH SERVICES IN SCHEMA {config.prefix}.APP")
                exists = any(r["name"] == config.service.split(".")[-1] for r in services)
                if exists:
                    db.run(f"ALTER CORTEX SEARCH SERVICE {config.service} {operation}")
                elif operation == "RESUME":
                    raise ValueError("No search service exists; run deploy after enabling AI")
                if operation == "SUSPEND":
                    warehouses = db.run(f"SHOW WAREHOUSES LIKE {literal(config.warehouse)}")
                    matching = [r for r in warehouses if r["name"] == config.warehouse]
                    if len(matching) != 1:
                        raise ValueError("Configured warehouse is missing or ambiguous")
                    if matching[0]["state"] != "SUSPENDED":
                        db.run(f"ALTER WAREHOUSE {config.warehouse} SUSPEND")
                result = {
                    "operation": operation,
                    "service_exists": exists,
                    "service": config.service,
                    "warehouse": config.warehouse,
                }
        # Raw tool evidence stays in ignored files; show only the useful answer for ask.
        print(
            json.dumps({k: v for k, v in result.items() if k != "response"}, indent=2, default=str)
        )
    except Error as exc:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = config.state_dir / "failures" / f"{stamp}-{args.command}.json"
        write_json(
            target,
            {
                "command": args.command,
                "error": str(exc),
                "query_id": exc.sfqid,
                "snapshot_id": config.snapshot,
            },
        )
        print(f"Snowflake error: {exc}\nEvidence: {target}", file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
