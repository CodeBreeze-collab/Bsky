from google import genai
import json
import os

# Configure Gemini client
client = genai.Client(api_key="AIzaSyDUVScEv1IRiTmXiKoLl7eNY4Pj3twL648")


def clean_llm_output(text: str) -> str:
    """Remove markdown code fences if the model accidentally adds them."""
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    return text


def process_animal_posts(input_file, output_file):
    system_instructions = (
        "You are a data enrichment and filtering assistant. "
        "You receive JSONL objects that contain a 'text' field representing social media posts.\n\n"

        "Your tasks:\n"
        "1. Keep ONLY posts that are clearly about a pet or animal available for adoption, rescue, or needing a home.\n"
        "2. If a post is NOT about a pet adoption, OMIT it completely from the output.\n"
        "3. For valid adoption posts, add three new fields: 'city', 'state', and 'country'.\n"
        "4. Infer location from the 'text' field using clues such as hashtags, place names, rescues/shelters, "
        "phone numbers, or phone area codes (example: 408 → California, USA).\n"
        "5. If a location field cannot be inferred, return an empty string.\n"
        "6. For UK locations (Manchester, Sheffield, etc), the 'state' field must be an empty string.\n"
        "7. Do NOT change any existing fields.\n"
        "8. Return ONLY valid JSONL objects for the posts that qualify as pet adoption posts.\n"
        "9. Do NOT include markdown, explanations, comments, or code fences.\n"
    )

    with open(input_file, "r", encoding="utf-8") as f_in, \
         open(output_file, "w", encoding="utf-8") as f_out:

        batch = []

        for line in f_in:
            if line.strip():
                batch.append(line.strip())

            if len(batch) >= 10:
                process_batch(batch, system_instructions, f_out)
                batch = []

        if batch:
            process_batch(batch, system_instructions, f_out)

    print(f"Success! Tagged data saved to: {output_file}")


def process_batch(batch, system_instructions, f_out):
    raw_input = "\n".join(batch)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config={
            "system_instruction": system_instructions,
            "response_mime_type": "application/json",
        },
        contents=raw_input,
    )

    cleaned = clean_llm_output(response.text)

    # Validate each JSON line before writing
    for line in cleaned.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            json.loads(line)
            f_out.write(line + "\n")
        except json.JSONDecodeError:
            print("Skipping invalid JSON line:", line)


if __name__ == "__main__":
    bsky_search_results_ = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/"

    process_animal_posts(
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/raw/manual_1630.jsonl",
        "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/search_results/location_tagged/03-09-2026/manual_03-09-2026-1630-loc_tagged.jsonl"
    )