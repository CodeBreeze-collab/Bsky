import json
from pathlib import Path
import re
from pypdf import PdfReader

# Directories and paths
MY_STORES_DIR = Path(
    "/Users/hdon/Desktop/go-affpro-pages/goaffpro-my-stores/my-store-pages"
)
OUTPUT_JSONL = Path(
    "/Users/hdon/Desktop/go-affpro-pages/my_stores.jsonl"
)


def parse_pdf_text(pdf_path):
  """Extracts all text from a PDF file."""
  reader = PdfReader(pdf_path)
  text = ""
  for page in reader.pages:
    page_text = page.extract_text()
    if page_text:
      text += page_text + "\n"
  return text


def extract_store_records(text):
  """Extracts store URL and ID records from text."""
  records = []

  # Regex patterns tailored for GoAffPro 'My Stores' layout
  # Adjust patterns if your PDF uses different field key names
  url_pattern = re.compile(
      r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", re.IGNORECASE
  )
  id_pattern = re.compile(
      r"(?:ID|Store ID|Store_ID)[:\s]*([a-zA-Z0-9-_]+)", re.IGNORECASE
  )

  lines = text.split("\n")
  current_url = None
  current_id = None

  for line in lines:
    line = line.strip()

    url_match = url_pattern.search(line)
    id_match = id_pattern.search(line)

    if url_match and not current_url:
      current_url = url_match.group(0)

    if id_match and not current_id:
      current_id = id_match.group(1)

    # Save and reset when a complete record (url + id) is found
    if current_url and current_id:
      records.append({
          "store_url": current_url,
          "store_id": current_id,
      })
      current_url = None
      current_id = None

  return records


def main():
  OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
  all_records = []

  pdf_files = list(MY_STORES_DIR.glob("*.pdf"))
  print(f"Found {len(pdf_files)} PDF files in {MY_STORES_DIR}")

  for pdf_path in pdf_files:
    try:
      text = parse_pdf_text(pdf_path)
      stores = extract_store_records(text)
      all_records.extend(stores)
    except Exception as e:
      print(f"Error reading {pdf_path.name}: {e}")

  # Write out to .jsonl
  with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
    for record in all_records:
      f.write(json.dumps(record) + "\n")

  print(f"Successfully wrote {len(all_records)} records to {OUTPUT_JSONL}")


if __name__ == "__main__":
  main()