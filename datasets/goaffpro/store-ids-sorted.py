import json
from pathlib import Path
import re
import unicodedata


def normalize_text(text):
  if not text:
    return ""
  return unicodedata.normalize("NFKC", str(text)).strip().lower()


def clean_store_id(store_id):
  if not store_id:
    return ""
  s = normalize_text(store_id)
  s = re.sub(r"store$", "", s, flags=re.I)
  return s.strip()


def export_sorted_store_data():
  pdf_output_json = "extracted_stores_output.json"
  output_txt = "sorted_store_ids.txt"

  if not Path(pdf_output_json).exists():
    print(f"Error: '{pdf_output_json}' not found.")
    return

  print(f"Loading data from '{pdf_output_json}'...")
  with open(pdf_output_json, "r", encoding="utf-8") as f:
    pdf_records = json.load(f)

  store_ids = set()
  store_urls = set()

  for rec in pdf_records:
    raw_id = rec.get("store_id")
    raw_url = rec.get("store_url")

    cleaned_id = clean_store_id(raw_id) if raw_id else ""
    if cleaned_id and cleaned_id != "null":
      store_ids.add(cleaned_id)

    if raw_url:
      store_urls.add(str(raw_url).strip())

  # Helper to sort IDs naturally (numeric if possible, otherwise alphabetical)
  def sort_key(val):
    try:
      return (0, int(val))
    except ValueError:
      return (1, str(val))

  sorted_ids = sorted(list(store_ids), key=sort_key)
  sorted_urls = sorted(list(store_urls))

  print(
      f"Found {len(sorted_ids)} unique store IDs and {len(sorted_urls)} unique"
      " URLs."
  )

  # Write sorted store IDs and URLs to text file
  with open(output_txt, "w", encoding="utf-8") as out:
    out.write("=== SORTED UNIQUE STORE IDS ===\n")
    for sid in sorted_ids:
      out.write(f"{sid}\n")

    out.write("\n" + "=" * 50 + "\n")
    out.write("=== UNIQUE STORE URLS ===\n")
    for surl in sorted_urls:
      out.write(f"{surl}\n")

  print(f"Successfully exported sorted lists to '{output_txt}'.")


if __name__ == "__main__":
  export_sorted_store_data()