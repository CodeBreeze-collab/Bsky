import json
import unicodedata
from pathlib import Path
import re


def normalize_text(text):
    """Normalizes unicode characters (e.g., ligatures like 'ﬁ' -> 'fi') and converts to lowercase."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return text.strip().lower()


def clean_store_id(store_id):
    """Cleans store IDs by normalizing text and removing trailing 'store' text."""
    if not store_id:
        return ""
    s = normalize_text(store_id)
    s = re.sub(r"store$", "", s, flags=re.I)
    return s.strip()


def is_valid_store_id(store_id):
    """Validates that a store id is not a generic short code or UI artifact (e.g., 'es', 'en', 's', etc.)."""
    if not store_id or not isinstance(store_id, str):
        return False

    cleaned_id = clean_store_id(store_id)
    if not cleaned_id or cleaned_id == "null":
        return False

    # Blacklist of known false-positive codes/artifacts found in logs
    blacklisted_ids = {'es', 'en', 'ge', 'or', 'ay', 's', 'e'}
    if cleaned_id in blacklisted_ids:
        return False

    # Ignore IDs that are too short to be unique merchant identifiers (minimum length 3)
    if len(cleaned_id) < 3:
        return False

    return True


def normalize_url(url):
    """Normalizes store URLs for robust matching."""
    if not url:
        return ""
    u = normalize_text(url)
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.rstrip("/")
    return u


def is_valid_merchant_url(url):
    """Validates that the URL is a real merchant domain and not a generic platform placeholder."""
    if not url or not isinstance(url, str):
        return False

    n_url = normalize_url(url)
    if not n_url or n_url == "null":
        return False

    # Filter out generic directory or platform links
    if 'goaffpro.com' in n_url:
        if 'store' in n_url or 'affiliate' in n_url:
            return False

    return True


def enrich_stores():
    pdf_output_json = "extracted_stores_output-all.json"
    input_jsonl = "my_stores.jsonl"
    output_jsonl = "enriched_stores-all.jsonl"

    if not Path(pdf_output_json).exists():
        print(f"Error: '{pdf_output_json}' not found.")
        return

    print(f"Loading PDF extraction data from '{pdf_output_json}'...")
    with open(pdf_output_json, "r", encoding="utf-8") as f:
        pdf_records = json.load(f)

    id_map = {}
    url_map = {}

    for rec in pdf_records:
        commission = rec.get("commission")
        source_file = rec.get("source_file")

        if not commission:
            continue

        raw_id = rec.get("store_id")
        if raw_id and is_valid_store_id(raw_id):
            c_id = clean_store_id(raw_id)
            id_map[c_id] = {"commission": commission, "source_file": source_file}

        raw_url = rec.get("store_url")
        if raw_url and is_valid_merchant_url(raw_url):
            n_url = normalize_url(raw_url)
            url_map[n_url] = {"commission": commission, "source_file": source_file}

    print(
        f"Built lookup tables: {len(id_map)} unique IDs, {len(url_map)} unique"
        " URLs."
    )

    if not Path(input_jsonl).exists():
        print(f"Error: '{input_jsonl}' not found.")
        return

    print(
        f"Enriching records from '{input_jsonl}' and printing comparison"
        " details...\n"
    )
    matched_by_id = 0
    matched_by_url = 0
    unmatched_count = 0
    total_count = 0

    with open(input_jsonl, "r", encoding="utf-8") as infile, open(
            output_jsonl, "w", encoding="utf-8"
    ) as outfile:
        for line_num, line in enumerate(infile, 1):
            line = line.strip()
            if not line:
                continue
            total_count += 1

            try:
                record = json.loads(line)
                raw_id = record.get("store_id")
                raw_url = record.get("store_url")

                c_id = clean_store_id(raw_id) if raw_id else ""
                n_url = normalize_url(raw_url) if raw_url else ""

                match_source = None
                match_data = None

                # Strategy 1: Try matching by valid store_id
                if raw_id and is_valid_store_id(raw_id) and c_id in id_map:
                    match_data = id_map[c_id]
                    match_source = "ID"
                    matched_by_id += 1

                # Strategy 2: Fallback to matching by valid normalized store_url
                if not match_data and raw_url and is_valid_merchant_url(raw_url) and n_url in url_map:
                    match_data = url_map[n_url]
                    match_source = "URL"
                    matched_by_url += 1

                # Print comparison log for this entry
                print(f"[Store #{total_count}]")
                print(
                    f"  - Raw ID: '{raw_id}' -> Cleaned ID: '{c_id}' | Valid ID? {is_valid_store_id(raw_id) if raw_id else False} | Found in PDF ID Map? {c_id in id_map if c_id else False}"
                )
                print(
                    f"  - Raw URL: '{raw_url}' -> Normalized URL: '{n_url}' | Valid URL? {is_valid_merchant_url(raw_url) if raw_url else False} | Found in PDF URL Map? {n_url in url_map if n_url else False}"
                )

                if match_source:
                    print(f"  -> SUCCESS: Matched via {match_source}")
                else:
                    print("  -> FAILED: No match found")
                    unmatched_count += 1
                print("-" * 60)

                if match_data:
                    record["commission"] = match_data["commission"]
                    record["source_file"] = match_data["source_file"]
                else:
                    record["commission"] = None
                    record["source_file"] = None

                outfile.write(json.dumps(record) + "\n")

            except json.JSONDecodeError:
                print(f"Warning: Skipping malformed JSON line {line_num}.")

    print("\n" + "=" * 40)
    print("Enrichment complete!")
    print(f"Total stores evaluated: {total_count}")
    print(f"  - Matched by Store ID: {matched_by_id}")
    print(f"  - Matched by Store URL: {matched_by_url}")
    print(f"  - Total Successfully Matched: {matched_by_id + matched_by_url}")
    print(f"  - Unmatched: {unmatched_count}")
    print(f"Saved output to: {output_jsonl}")
    print("=" * 40)


if __name__ == "__main__":
    enrich_stores()