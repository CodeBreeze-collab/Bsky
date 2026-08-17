import json
from pathlib import Path
import re
from pypdf import PdfReader


def parse_available_stores(data):
  records = []

  for page_index, page_data in enumerate(data):
    raw_text = page_data.get("text", "")

    # FIX: Normalize spaced-out characters typical in PDFs (e.g., "S t o r e   I D" -> "Store ID")
    # This collapses single-character spacing gaps while preserving actual word spaces.
    text = re.sub(r"(?<=\b\w)\s(?=\w\b)", "", raw_text)

    # 1. Regex to match Store ID, Store #, or standalone ID tokens
    store_ids = re.findall(
        r"(?:Store\s*ID|Store\s*\#|ID|\#)[:\s]*([a-zA-Z0-9-_]+)", text, re.I
    )
    urls = re.findall(r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", text)
    commissions = re.findall(
        r"([0-9]+%\s*(?:commission)?|commission[:\s]*[0-9]+%|[0-9]+%|\$[0-9]+(?:\.[0-9]{2})?)",
        text,
        re.I,
    )

    # Filter out common UI/nav URLs if they accidentally get grabbed
    urls = [
        u
        for u in urls
        if "goaffpro.com/affiliate/stores/search" not in u
        and "goaffpro.com/afﬁliate/stores/search" not in u
    ]

    # 2. If counts align reasonably well, zip them directly
    if store_ids and len(store_ids) == len(urls):
      for i, url in enumerate(urls):
        s_id = store_ids[i] if i < len(store_ids) else None
        comm = commissions[i] if i < len(commissions) else None
        records.append({
            "store_url": url,
            "store_id": s_id,
            "commission": comm.strip() if comm else None,
        })
    else:
      # 3. Fallback: Line-by-line state machine on the normalized text
      lines = text.split("\n")
      current_store_id = None
      current_url = None
      current_commission = None

      for line in lines:
        line = line.strip()
        if not line:
          continue

        s_match = re.search(
            r"(?:Store\s*ID|Store\s*\#|ID|\#)[:\s]*([a-zA-Z0-9-_]+)",
            line,
            re.I,
        )
        u_match = re.search(r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", line)
        c_match = re.search(
            r"([0-9]+%|\$[0-9]+(?:\.[0-9]{2})?|commission[:\s]*[0-9]+%)",
            line,
            re.I,
        )

        if s_match:
          if current_store_id or current_url or current_commission:
            records.append({
                "store_url": current_url,
                "store_id": current_store_id,
                "commission": current_commission,
            })
            current_url, current_commission = None, None
          current_store_id = s_match.group(1)

        if (
            u_match
            and not current_url
            and "goaffpro.com" not in u_match.group(1)
        ):
          current_url = u_match.group(1)

        if c_match and not current_commission:
          current_commission = c_match.group(1)

      # Append the final record on the page
      if current_store_id or current_url or current_commission:
        records.append({
            "store_url": current_url,
            "store_id": current_store_id,
            "commission": current_commission,
        })

  return records


def process_pdf_folder(folder_path):
  all_records = []
  folder = Path(folder_path)

  if not folder.exists():
    print(f"Error: Folder '{folder_path}' does not exist.")
    return all_records

  pdf_files = list(folder.glob("*.pdf"))
  if not pdf_files:
    print(f"No PDF files found in '{folder_path}'.")
    return all_records

  print(f"Found {len(pdf_files)} PDF file(s) in '{folder_path}'. Processing...")

  for pdf_path in pdf_files:
    print(f"Reading: {pdf_path.name}")
    try:
      reader = PdfReader(str(pdf_path))
      page_data_list = []
      for page in reader.pages:
        text = page.extract_text() or ""
        page_data_list.append({"text": text})

      file_records = parse_available_stores(page_data_list)

      for rec in file_records:
        rec["source_file"] = pdf_path.name

      all_records.extend(file_records)
      print(f" -> Extracted {len(file_records)} store records from {pdf_path.name}")
    except Exception as e:
      print(f" -> Error processing {pdf_path.name}: {e}")

  return all_records


def main():
  # Point this to your actual folder containing the PDFs
  input_folder_path = (
      "/Users/hdon/Desktop/go-affpro-pages/goaffpro-available-pages/"
  )
  extracted_records = process_pdf_folder(input_folder_path)

  output_file = "extracted_stores_output-all.json"
  with open(output_file, "w", encoding="utf-8") as f:
    json.dump(extracted_records, f, indent=4)

  print("\n" + "=" * 40)
  print(f"Processing complete!")
  print(f"Total stores successfully extracted: {len(extracted_records)}")
  print(f"Saved output to: {output_file}")
  print("=" * 40)


if __name__ == "__main__":
  main()