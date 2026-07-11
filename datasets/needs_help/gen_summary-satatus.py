import os
import json


INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help/"
OUTPUT_DIR = "/bsky/datasets/needs_help_v2_"


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
    """
    Recursively search all values in JSON object
    for NYCACC (case-insensitive).
    """
    if isinstance(obj, dict):
        return any(contains_nycacc(v) for v in obj.values())

    elif isinstance(obj, list):
        return any(contains_nycacc(v) for v in obj)

    elif isinstance(obj, str):
        return "nycacc" in obj.lower()

    return False


def process_file(input_file, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as infile, \
         open(output_file, "w", encoding="utf-8") as outfile:

        for line in infile:
            if not line.strip():
                continue

            record = json.loads(line)

            # Replace status
            record["final_status"] = normalize_status(
                record.get("final_status", "")
            )

            # NYCACC detection
            if contains_nycacc(record):
                record["state"] = "NY"

            outfile.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


def main():
    for root, _, files in os.walk(INPUT_DIR):
        for filename in files:

            if filename != "animal_centric_posts-w-loc-2.jsonl":
                continue

            input_file = os.path.join(root, filename)

            # Preserve relative folder structure
            relative_dir = os.path.relpath(root, INPUT_DIR)
            output_dir = os.path.join(OUTPUT_DIR, relative_dir)

            output_file = os.path.join(
                output_dir,
                filename
            )

            print(f"{input_file} -> {output_file}")

            process_file(
                input_file,
                output_file
            )


if __name__ == "__main__":
    main()