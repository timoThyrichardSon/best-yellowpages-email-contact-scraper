thonimport argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure src directory is on sys.path so we can import local modules
CURRENT_FILE = Path(__file__).resolve()
SRC_DIR = CURRENT_FILE.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from extractors.yellowpages_parser import YellowPagesScraper  # type: ignore
from extractors.contact_scanner import ContactScanner  # type: ignore
from outputs.exporters import export_to_json, export_to_csv  # type: ignore

def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

def load_config(config_path: str | None) -> Dict[str, Any]:
    default_config = {
        "base_url": "https://www.yellowpages.com",
        "timeout": 15,
        "request_delay": 0.0,
        "max_results": 50,
        "sort": "bestmatch",
        "proxy": None,
        "output": {
            "directory": "data",
            "format": "json",  # json or csv
            "filename_prefix": "yellowpages_results",
        },
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            )
        },
    }

    if not config_path:
        return default_config

    config_file = Path(config_path)
    if not config_file.is_file():
        logging.warning("Config file '%s' not found. Using default configuration.", config_path)
        return default_config

    try:
        with config_file.open("r", encoding="utf-8") as f:
            user_config = json.load(f)
        # shallow merge user config into default
        merged = default_config | {k: v for k, v in user_config.items() if v is not None}
        # nested output & headers merge
        if "output" in user_config:
            merged["output"] = default_config["output"] | user_config["output"]
        if "headers" in user_config:
            merged["headers"] = default_config["headers"] | user_config["headers"]
        return merged
    except Exception as exc:  # noqa: BLE001
        logging.error("Failed to read config file '%s': %s", config_path, exc)
        return default_config

def enrich_with_contacts(
    base_records: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    scanner = ContactScanner(
        timeout=config.get("timeout", 15),
        headers=config.get("headers") or {},
        proxy=config.get("proxy"),
    )

    enriched: List[Dict[str, Any]] = []
    for record in base_records:
        website = record.get("website") or "Not Found"
        contact_data = scanner.scan_website(website)
        combined = record | contact_data
        enriched.append(combined)
    return enriched

def run_scraper(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    setup_logging(args.verbose)

    scraper = YellowPagesScraper(
        base_url=config.get("base_url", "https://www.yellowpages.com"),
        timeout=config.get("timeout", 15),
        headers=config.get("headers") or {},
        proxy=config.get("proxy"),
        request_delay=config.get("request_delay", 0.0),
    )

    max_results = args.max_results or config.get("max_results", 50)
    sort = args.sort or config.get("sort", "bestmatch")

    logging.info(
        "Starting Yellow Pages scrape: keyword='%s', location='%s', max_results=%d, sort='%s'",
        args.keyword,
        args.location,
        max_results,
        sort,
    )
    base_records = scraper.search(
        keyword=args.keyword,
        location=args.location,
        max_results=max_results,
        sort=sort,
    )

    logging.info("Found %d base listings. Enriching with contact details…", len(base_records))
    results = enrich_with_contacts(base_records, config)

    output_cfg = config.get("output", {})
    output_dir = Path(output_cfg.get("directory") or "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    filename_prefix = output_cfg.get("filename_prefix") or "yellowpages_results"

    if args.output:
        outfile = Path(args.output)
    else:
        outfile = output_dir / f"{filename_prefix}.{args.format or output_cfg.get('format', 'json')}"

    fmt = (args.format or output_cfg.get("format") or "json").lower()
    if fmt == "csv":
        export_to_csv(results, outfile)
    else:
        export_to_json(results, outfile)

    logging.info("Scraping complete. Saved %d records to '%s'.", len(results), outfile)
    print(f"Saved {len(results)} records to {outfile}")

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Best Yellowpages Email & Contact Scraper\n"
            "Scrapes Yellow Pages for business listings and enriches them "
            "with discovered emails and social media links."
        )
    )

    parser.add_argument(
        "--keyword",
        required=True,
        help="Search term such as 'dentist', 'coffee shop', or 'plumber'.",
    )
    parser.add_argument(
        "--location",
        required=True,
        help="Location such as 'Los Angeles, CA' or ZIP code like '90001'.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of listings to process (overrides config).",
    )
    parser.add_argument(
        "--sort",
        choices=["bestmatch", "distance", "rating", "name"],
        default=None,
        help="Sorting mode for Yellow Pages search results.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a JSON configuration file based on src/config/settings.example.json.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default=None,
        help="Output format (json or csv). Overrides config.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If not specified, constructed from config.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (-v, -vv).",
    )

    return parser

def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    run_scraper(args)

if __name__ == "__main__":
    main()