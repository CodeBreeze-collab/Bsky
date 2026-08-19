import json
from pathlib import Path


def main():
  # Define input and output file paths
  input_path = Path(
      "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-cleaned.jsonl"
  )
  output_path = input_path.with_name(
      "enriched_stores-w-products-filtered-final.jsonl"
  )

  print(f"Processing: {input_path.name}")

  omitted_count = 0
  kept_count = 0

  with open(input_path, "r", encoding="utf-8") as infile, open(
      output_path, "w", encoding="utf-8"
  ) as outfile:
    for line in infile:
      line_stripped = line.strip()
      if not line_stripped:
        continue

      try:
        data = json.loads(line_stripped)
      except json.JSONDecodeError:
        continue  # Skip malformed lines if any exist

      base_url = data.get("baseUrl", "")
      commission = data.get("commission")

      # Omit if:
      # 1. "https://goaffpro.com" is in the baseUrl
      # 2. "commission" is null (Python's None)
      if "https://goaffpro.com" in base_url or commission is None:
        omitted_count += 1
        continue

      # Write valid lines back out
      outfile.write(line_stripped + "\n")
      kept_count += 1

  print(f"Filtering complete!")
  print(f"- Kept records: {kept_count}")
  print(f"- Omitted records: {omitted_count}")
  print(f"- Output saved to: {output_path}")


if __name__ == "__main__":
  main()