import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

import argparse
import os
from pathlib import Path

from ncdb.api.database import Database
from ncdb_monitor.generate import generate_website_data
from ncdb_monitor.render import generate_html

from ncdb.scanners import list_scanners

from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer


def cmd_scan(args):
    logger.info("Scanning data into database")

    db = Database(args.database)

    logger.info(f"Database: {args.database}")
    logger.info(f"Data root: {args.data_dir}")
    logger.info(f"Scanner: {args.scanner}")

    report = db.scan(
        data_root=args.data_dir,
        n_cycles=args.n_cycles,
        scanner=args.scanner
    )

    logger.info(
        f"Scan completed: "
        f"{report['cycles_scanned']} cycles"
    )


def cmd_generate(args):
    logger.info("Generating website data")

    db = Database(args.database)

    logger.info(f"Database: {args.database}")
    logger.info(f"Website dir: {args.website_dir}")
    logger.info(f"Generate 2D Snapshots: {args.snapshots}")

    website_dir = Path(args.website_dir)

    generate_website_data(
        db=db,
        website_dir=website_dir,
        generate_snapshots=args.snapshots
    )


def cmd_render(args):
    logger.info(f"Rendering: Website dir: {args.website_dir}")
    website_dir = Path(args.website_dir)
    generate_html(website_dir=website_dir)


def save_run_report(website_dir, run_report):
    import json
    from pathlib import Path

    runs_dir = Path(website_dir) / "runs"
    runs_dir.mkdir(exist_ok=True)

    start_time = run_report["start_time"]
    run_file = runs_dir / f"{start_time}.json"

    with open(run_file, "w") as f:
        json.dump(run_report, f, indent=2)


def old_cmd_run(args):
    from datetime import datetime
    import time

    start = time.time()
    start_time = datetime.utcnow().isoformat() + "Z"

    logger.info("=== NCDB Monitor PIPELINE ===")

    cmd_scan(args)
    cmd_generate(args)
    cmd_render(args)

    end = time.time()
    end_time = datetime.utcnow().isoformat() + "Z"

    run_report = {
        "status": "success",
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": round(end - start, 3),
        "database": args.database,
        "website_dir": str(args.website_dir),
        "scanner": args.scanner,
        "n_cycles": args.n_cycles,
        "data_dir": str(args.data_dir),
        "snapshots_generated": args.snapshots,
    }

    save_run_report(args.website_dir, run_report)
    return run_report

def cmd_run(args):
    from datetime import datetime
    import time

    start = time.time()
    start_time = datetime.utcnow().isoformat() + "Z"

    logger.info("=== NCDB Monitor PIPELINE ===")

    cmd_scan(args)
    
    end_time = datetime.utcnow().isoformat() + "Z"
    run_report = {
        "status": "success",
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": round(time.time() - start, 3),
        "database": args.database,
        "website_dir": str(args.website_dir),
        "scanner": args.scanner,
        "n_cycles": args.n_cycles,
        "data_dir": str(args.data_dir),
        "snapshots_generated": args.snapshots,
    }
    save_run_report(args.website_dir, run_report)

    cmd_generate(args)
    cmd_render(args)

    return run_report


class ReusableTCPServer(TCPServer):
    allow_reuse_address = True


def cmd_serve(args):
    website_dir = Path(args.website_dir).resolve()
    port = args.port

    logger.info(f"Serving {website_dir} at http://localhost:{port}")
    os.chdir(website_dir)

    handler = SimpleHTTPRequestHandler
    with ReusableTCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down server")
            httpd.shutdown()


def build_parser():
    parser = argparse.ArgumentParser(
        description="NCDB monitoring application"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    snapshot_parser = argparse.ArgumentParser(add_help=False)
    snapshot_parser.add_argument(
        "--snapshots",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable or disable 2D map snapshot generation (default: false)"
    )

    available_scanners = list_scanners()

    #
    # scan
    #
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan filesystem data into database"
    )
    scan_parser.add_argument(
        "--scanner", required=True, choices=available_scanners, help="Scanner type to use"
    )
    scan_parser.add_argument(
        "--n-cycles", type=int, default=-1, help="Number of cycles to scan"
    )
    scan_parser.add_argument(
        "--data-dir", required=True, help="Root data directory"
    )
    scan_parser.add_argument(
        "--database", required=True, help="Path to ncdb database"
    )
    scan_parser.set_defaults(func=cmd_scan)

    #
    # generate
    #
    gen_parser = subparsers.add_parser(
        "generate",
        parents=[snapshot_parser],  # Inherit snapshot switch
        help="Generate website data"
    )
    gen_parser.add_argument(
        "--database", required=True, help="Path to ncdb database"
    )
    gen_parser.add_argument(
        "--website-dir", required=True, help="Website output directory"
    )
    gen_parser.set_defaults(func=cmd_generate)

    #
    # render
    #
    render_parser = subparsers.add_parser(
        "render",
        help="Render website HTML"
    )
    render_parser.add_argument(
        "--website-dir", required=True, help="Website output directory"
    )
    render_parser.set_defaults(func=cmd_render)

    #
    # run
    #
    run_parser = subparsers.add_parser(
        "run",
        parents=[snapshot_parser],  # Inherit snapshot switch
        help="Run monitor pipeline"
    )
    run_parser.add_argument(
        "--scanner", required=True, choices=available_scanners, help="Scanner type to use"
    )
    run_parser.add_argument(
        "--n-cycles", type=int, default=-1, help="Number of cycles to scan"
    )
    run_parser.add_argument(
        "--data-dir", required=True, help="Root data directory"
    )
    run_parser.add_argument(
        "--database", required=True, help="Path to ncdb database"
    )
    run_parser.add_argument(
        "--website-dir", required=True, help="Website output directory"
    )
    run_parser.set_defaults(func=cmd_run)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
