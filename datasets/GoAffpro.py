import os
import logging
from pathlib import Path
import pdfplumber

# Suppress the noisy pdfminer font warnings completely
logging.getLogger("pdfminer").setLevel(logging.ERROR)


def extract_instant_approval_stores(pdf_dir):
    """
    Scans all PDF files, suppresses font warnings, writes links
    to the output file in real-time, and avoids duplicate entries.
    """
    seen_stores = set()
    output_file = "/Users/hdon/Desktop/go-affpro-pages/instant_approval_stores.txt"

    # Open output file immediately to write results in real-time
    with open(output_file, "w") as f:
        pdf_files = list(Path(pdf_dir).glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in directory: {pdf_dir}")
            return

        for pdf_path in pdf_files:
            print(f"Processing: {pdf_path.name}")
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if not text:
                        continue

                    lines = [line.strip() for line in text.split('\n') if line.strip()]

                    for i, line in enumerate(lines):
                        if "Instant Access" in line or "Instant Approval" in line:
                            for j in range(max(0, i - 8), i):
                                candidate = lines[j]
                                cleaned = candidate.replace("https://", "").replace("http://", "").replace("www.", "")

                                if "." in cleaned and not any(kw in cleaned.lower() for kw in [
                                    'currency', 'commission', 'cookie', 'registration', 'store id', 'goaffpro', 'page',
                                    'usd'
                                ]):
                                    # If it's a new store, write it immediately in real-time
                                    if candidate not in seen_stores:
                                        seen_stores.add(candidate)
                                        f.write(f"{candidate}\n")
                                        f.flush()  # Ensure it writes to disk immediately
                                        print(f"  [Found Live] {candidate}")
                                    break

    print(f"\nFinished! Total unique stores found: {len(seen_stores)}")
    print(f"Results saved to {output_file}")


if __name__ == "__main__":
    pdf_directory = "/Users/hdon/Desktop/go-affpro-pages/"
    extract_instant_approval_stores(pdf_directory)