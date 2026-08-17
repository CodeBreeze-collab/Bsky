import json
import os
from google import genai

# Configuration
INPUT_DIR = "/Users/hdon/Desktop/Desktop-05-18/how-did/01-18-2025-Desktop/Desktop-01-08-2026/DS-12-15-2025/Desktop-to-sort/JPG_GT100KB_LT1MB/christine/india/awin/awin_merchants/"
OUTPUT_FILE = "merchants_summary.jsonl"
MODEL_ID = "gemini-2.5-flash"  # Fast and efficient model for text tasks

# Initialize the Gemini client (picks up GEMINI_API_KEY automatically)
client = genai.Client()


def main():
  if not os.path.exists(INPUT_DIR):
    print(
        f"Error: Directory '{INPUT_DIR}' not found. Please run your shell"
        " script first."
    )
    return

  json_files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".json")]

  if not json_files:
    print(f"No JSON files found in '{INPUT_DIR}'.")
    return

  print(
      f"Found {len(json_files)} merchant files. Processing with Gemini"
      f" ({MODEL_ID})..."
  )

  # Open the .jsonl output file for writing
  with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
    for filename in json_files:
      filepath = os.path.join(INPUT_DIR, filename)

      try:
        with open(filepath, "r", encoding="utf-8") as f:
          data = json.load(f)

          # Extract info from programmeInfo
          programme_info = data.get("programmeInfo", {})
          merchant_id = programme_info.get("id")
          description = programme_info.get("description")

          if not merchant_id or not description:
            print(
                f"Skipping {filename}: Missing merchant ID or description data."
            )
            continue

          # Formulate the prompt for Gemini
          prompt = (
              "Based on the following merchant description, provide a single,"
              " concise sentence or blurb that clearly explains what kind of"
              f" products are sold.\n\nDescription: {description}"
          )

          # Call Gemini API
          response = client.models.generate_content(
              model=MODEL_ID,
              contents=prompt,
          )

          blurb = response.text.strip() if response.text else ""

          # Create the dictionary and write it as a JSON line
          line_data = {"merchant_id": merchant_id, "blurb": blurb}
          outfile.write(json.dumps(line_data) + "\n")

          print(f"Successfully processed merchant ID: {merchant_id}")

      except Exception as e:
        print(f"Error processing file {filename}: {e}")

  print(f"\nDone! Results successfully saved to '{OUTPUT_FILE}'.")


if __name__ == "__main__":
  main()