import os
import json
from google import genai
from pydantic import BaseModel
from datetime import datetime

# Define the exact structure we want back from the Gemini API
class LocationExtraction(BaseModel):
    country: str
    state_or_region: str
    city: str
    location_text_found: str

INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/to-correct/"
OUTPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/location_corrected_3/"

MODEL = "gemini-2.5-flash"

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

def parse_date_dir(dirname):
    try:
        return datetime.strptime(dirname, "%m-%d-%Y")
    except ValueError:
        return None

def get_sorted_date_dirs(input_dir):
    dirs = []
    if not os.path.exists(input_dir):
        return dirs
    for name in os.listdir(input_dir):
        path = os.path.join(input_dir, name)
        if os.path.isdir(path):
            dt = parse_date_dir(name)
            if dt:
                dirs.append((dt, path))
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs

def collect_text(obj):
    """Recursively collect all human-readable text fields."""
    texts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                texts.append(v)
            else:
                texts.extend(collect_text(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(collect_text(item))
    return texts

def normalize_status(status):
    if not status:
        return "Not Applicable / Unknown"

    s = status.lower().strip()

    # Priority matters: urgent overrides medical/rescue
    if any(x in s for x in [
        "euth", "kill command", "death row", "tbk",
        "to be killed", "scheduled for euthanasia",
        "at risk of euthanasia", "urgent",
        "out of time", "last call", "threatened"
    ]):
        return "Urgent Rescue Risk"

    if any(x in s for x in [
        "needs rescue", "rescue needed",
        "rescue only", "awaiting rescue",
        "rescue placement", "second chance",
        "advocacy/rescue"
    ]):
        return "Needs Rescue"

    if any(x in s for x in [
        "needs foster", "foster/adopt",
        "foster/adopter"
    ]):
        return "Needs Foster"

    if any(x in s for x in [
        "medical", "ill", "surgery",
        "vet", "treatment", "palliative",
        "special needs"
    ]):
        return "Medical Need"

    if any(x in s for x in [
        "needs adoption", "needs home",
        "forever home", "loving home",
        "rehoming", "looking for home",
        "placement"
    ]):
        return "Needs Adoption/Home"

    if any(x in s for x in [
        "available", "ready for adoption",
        "still available", "pre-adoption"
    ]):
        return "Available"

    if any(x in s for x in [
        "in foster", "fostered",
        "under care", "rehabilitation",
        "transitioning"
    ]):
        return "Fostered / Under Care"

    if any(x in s for x in [
        "adopted", "reclaimed",
        "reclaiming", "trial adoption"
    ]):
        return "Adopted / Reclaimed"

    if "sanctuary" in s:
        return "Sanctuary"

    if any(x in s for x in [
        "rescued", "safe",
        "with rescue", "with owner",
        "contained"
    ]):
        return "Rescued / Safe"

    if any(x in s for x in [
        "fund", "sponsorship",
        "pledge", "donation",
        "supplies"
    ]):
        return "Funding Needed"

    if any(x in s for x in [
        "unknown", "not applicable",
        "information only",
        "no urgent", "conflict"
    ]):
        return "Not Applicable / Unknown"

    return "Not Applicable / Unknown"

def contains_nycacc(obj):
    """Recursively search all values in JSON object for NYCACC (case-insensitive)."""
    if isinstance(obj, dict):
        return any(contains_nycacc(v) for v in obj.values())
    elif isinstance(obj, list):
        return any(contains_nycacc(v) for v in obj)
    elif isinstance(obj, str):
        return "nycacc" in obj.lower()
    return False

def extract_and_correct_location(text):
    prompt = f"""
You are auditing and correcting geographic information from animal rescue posts. 
Note: The source dataset may have mistakenly defaulted the country field to "USA". Your explicit job is to correct this.

Analyze the text to determine the true city, state/region, and country. 

Rules:
- If the text explicitly mentions or strongly implies a location outside the USA (e.g., 'England', 'Dublin', 'Ireland', 'London', 'UK', 'Australia'), map the country, state, and city accurately based on that context. Do not stick to the "USA" default.
- For locations inside the USA, ALWAYS return the state_or_region as a standard 2-letter abbreviation (e.g., 'California' must be 'CA', 'Texas' must be 'TX', 'New York' must be 'NY').
- Use empty strings if a specific metric (like city or state) is entirely unknown.
- Do not invent locations.
- Special handling for NYCACC: if 'NYCACC' appears, use: country="USA", state_or_region="NY", city="New York".

Text to analyze:
{text}
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": LocationExtraction,
            }
        )
        return json.loads(response.text)

    except Exception as e:
        print("Gemini error:", e)
        return {
            "country": "",
            "state_or_region": "",
            "city": "",
            "location_text_found": ""
        }

def load_existing_records(output_file):
    existing = {}
    if not os.path.exists(output_file):
        return existing
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                key = get_record_key(record)
                if key:
                    existing[key] = record
            except json.JSONDecodeError:
                continue
    return existing

def get_record_key(record):
    return record.get("animal_id") or record.get("post_url")

def process_file(input_file, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    existing_records = load_existing_records(output_file)

    if existing_records:
        print(f"   Found {len(existing_records)} existing records, resuming...")

    processed = 0
    skipped = 0
    gemini_calls = 0

    with open(input_file, "r", encoding="utf-8") as infile, \
         open(output_file, "a", encoding="utf-8") as outfile:

        for line in infile:
            if not line.strip():
                continue

            record = json.loads(line)
            key = get_record_key(record)

            # Deduplication / Resume support
            if key in existing_records:
                skipped += 1
                continue

            texts = collect_text(record)
            combined_text = "\n".join(texts)

            # 1. Location correction via Gemini API
            location = extract_and_correct_location(combined_text)
            gemini_calls += 1

            record["extracted_location"] = location

            # Override default country placeholders
            if location["country"].strip():
                record["country"] = location["country"]

            # Update state maps
            if location["state_or_region"].strip():
                record["state"] = location["state_or_region"]
            elif record.get("country") != "USA":
                record["state"] = ""

            # Update city maps
            if location["city"].strip():
                record["city"] = location["city"]

            # 2. Rule-based Status Normalization Step
            record["final_status"] = normalize_status(
                record.get("final_status", "")
            )

            # 3. Rule-based NYCACC fallback validation rule
            if contains_nycacc(record):
                record["state"] = "NY"
                record["country"] = "USA"

            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            processed += 1

    print(f"   Done: processed={processed}, skipped={skipped}, Gemini calls={gemini_calls}")

def main():
    date_dirs = get_sorted_date_dirs(INPUT_DIR)
    if not date_dirs:
        print(f"No date directories found in {INPUT_DIR}")
        return

    for dt, date_dir in date_dirs:
        print(f"\nProcessing date directory: {dt.strftime('%m-%d-%Y')}")

        for root, _, files in os.walk(date_dir):
            for filename in files:
                if filename != "animal_centric_posts-w-loc-2.jsonl":
                    continue

                input_file = os.path.join(root, filename)
                relative = os.path.relpath(root, INPUT_DIR)
                output_file = os.path.join(OUTPUT_DIR, relative, filename)

                print(f"   {input_file}")
                process_file(input_file, output_file)

if __name__ == "__main__":
    main()