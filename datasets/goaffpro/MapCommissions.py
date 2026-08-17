import os
import json
import re
import pdfplumber

# Define paths
PDF_DIR = "/Users/hdon/Desktop/go-affpro-pages/"
MY_STORES_DIR = os.path.join(PDF_DIR, "goaffpro-my-stores")
OUTPUT_JSONL = os.path.join(PDF_DIR, "goaffpro_stores_with_percentage-3.jsonl")


def parse_pdf_pages(pdf_dir):
    """Parses all goaffpro-page-*.pdf files and extracts store details."""
    store_catalog = {}

    pdf_files = [f for f in os.listdir(pdf_dir) if f.startswith("goaffpro-page-") and f.endswith(".pdf")]

    for pdf_file in sorted(pdf_files):
        pdf_path = os.path.join(pdf_dir, pdf_file)
        print(f"Processing {pdf_file}...")

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue

                chunks = text.split("Store ID:")
                for chunk in chunks[1:]:
                    lines = [line.strip() for line in chunk.strip().split("\n") if line.strip()]
                    if not lines:
                        continue

                    store_id = lines[0].split()[0].strip()

                    commission = None
                    currency = "USD"
                    cookie_duration = None

                    for line in lines:
                        if "Commission" in line:
                            comm_match = re.search(r"Commission\s+(.*)", line)
                            if comm_match:
                                commission = comm_match.group(1).strip()
                        if "Cookie Duration" in line:
                            cookie_match = re.search(r"Cookie Duration\s+(.*)", line)
                            if cookie_match:
                                cookie_duration = cookie_match.group(1).strip()
                        if "Currency" in line:
                            curr_match = re.search(r"Currency\s+(\w+)", line)
                            if curr_match:
                                currency = curr_match.group(1).strip()

                    store_catalog[store_id] = {
                        "store_id": store_id,
                        "commission": commission,
                        "currency": currency,
                        "cookie_duration": cookie_duration
                    }

    return store_catalog


def process_my_stores(my_stores_dir, store_catalog, output_path):
    """Reads only source store records from .jsonl files, maps commission data, and writes out updated JSONL."""
    print(f"\n[DEBUG] Checking my_stores_dir path: {my_stores_dir}")
    if not os.path.exists(my_stores_dir):
        print(f"[DEBUG] Error: My stores directory not found at {my_stores_dir}")
        return

    all_files = os.listdir(my_stores_dir)

    # Filter to ONLY process input store lists, ignoring old outputs or result files
    jsonl_files = [
        f for f in all_files
        if f.endswith(".jsonl")
           and not f.endswith("_with_pct.jsonl")
           and f != "enriched_stores.jsonl"
    ]
    print(f"[DEBUG] Found target source JSONL files to process: {jsonl_files}")

    matched_count = 0
    unmatched_count = 0

    with open(output_path, "w", encoding="utf-8") as outfile:
        for jsonl_file in jsonl_files:
            jsonl_path = os.path.join(my_stores_dir, jsonl_file)
            print(f"Processing JSONL file: {jsonl_file}...")

            with open(jsonl_path, "r", encoding="utf-8") as infile:
                for line_num, line in enumerate(infile, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        store_data = json.loads(line)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON on line {line_num} of {jsonl_file}: {e}")
                        continue

                    # Extract store_id and normalize to string
                    raw_store_id = store_data.get("store_id") or store_data.get("id")
                    store_id = str(raw_store_id).strip() if raw_store_id is not None else ""

                    # Map commission details if present in the catalog
                    if store_id in store_catalog:
                        store_data.update(store_catalog[store_id])
                        matched_count += 1
                    else:
                        unmatched_count += 1
                        store_data["commission"] = None
                        store_data["currency"] = "USD"
                        store_data["cookie_duration"] = None

                    outfile.write(json.dumps(store_data) + "\n")

    print(f"\nProcessing complete!")
    print(f"Matched stores: {matched_count}")
    print(f"Unmatched stores: {unmatched_count}")
    print(f"Output written to: {output_path}")


if __name__ == "__main__":
    catalog = parse_pdf_pages(PDF_DIR)
    print(f"Extracted {len(catalog)} stores from PDF catalog.")
    process_my_stores(MY_STORES_DIR, catalog, OUTPUT_JSONL)