thonimport csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)

def _ensure_parent_dir(path: Path) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

def export_to_json(records: Iterable[Dict[str, Any]], output_path: Path) -> None:
    data_list: List[Dict[str, Any]] = list(records)
    _ensure_parent_dir(output_path)

    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data_list, f, indent=2, ensure_ascii=False)
        logger.info("Successfully exported %d records to JSON at '%s'.", len(data_list), output_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to export JSON to '%s': %s", output_path, exc)
        raise

def export_to_csv(records: Iterable[Dict[str, Any]], output_path: Path) -> None:
    records_list: List[Dict[str, Any]] = list(records)
    _ensure_parent_dir(output_path)

    # Determine CSV columns. Start with core fields, then expand with any extras we see.
    core_fields = ["name", "address", "phone", "website", "emails"]
    social_platforms = [
        "linkedin",
        "facebook",
        "twitter",
        "tiktok",
        "pinterest",
        "instagram",
    ]
    fields = core_fields + [f"social_{p}" for p in social_platforms]

    extra_keys = set()
    for rec in records_list:
        for key in rec.keys():
            if key not in fields and key not in {"socialmedia"}:
                extra_keys.add(key)
    fields.extend(sorted(extra_keys))

    def flatten_record(rec: Dict[str, Any]) -> Dict[str, Any]:
        flat: Dict[str, Any] = {k: rec.get(k, "Not Found") for k in core_fields}
        # Emails as semicolon-separated string
        emails = rec.get("emails") or []
        if isinstance(emails, list):
            flat["emails"] = ";".join(emails)
        else:
            flat["emails"] = str(emails)

        social = rec.get("socialmedia") or {}
        if not isinstance(social, dict):
            social = {}

        for platform in social_platforms:
            links = social.get(platform) or []
            if isinstance(links, list):
                flat[f"social_{platform}"] = ";".join(links)
            else:
                flat[f"social_{platform}"] = str(links)

        # Add remaining keys
        for key in extra_keys:
            flat[key] = rec.get(key, "")

        return flat

    try:
        with output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for rec in records_list:
                writer.writerow(flatten_record(rec))
        logger.info("Successfully exported %d records to CSV at '%s'.", len(records_list), output_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to export CSV to '%s': %s", output_path, exc)
        raise