import json
import os
from google import genai
from google.genai import types

# Initialize the Gemini client
# (Ensure your GEMINI_API_KEY environment variable is set)
client = genai.Client()


def enrich_store_summary(base_url, store_name):
    prompt = f"""
    Analyze the online store named '{store_name}' with URL '{base_url}'.
    Write a single short sentence summarizing the products on the merchant site (e.g., "Yappy sells customized pet apparel and accessories").

    You MUST output your response strictly as a JSON object with the following key:
    - "summary": a short sentence about the products on the merchant site

    Do not include any markdown code blocks (like ```json) or extra text, just raw JSON.
    """

    config = types.GenerateContentConfig(
        temperature=0.1,
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )

        if not response.text:
            print(f"Warning: Empty response received for {base_url}")
            return None

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        return json.loads(raw_text.strip())
    except Exception as e:
        print(f"Error processing {base_url}: {e}")
        return None


def process_jsonl(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            if not line.strip():
                continue
            data = json.loads(line)

            # Trigger API call only if summary is missing
            if not data.get("summary"):
                print(f"Generating summary for: {data.get('name')} ({data.get('baseUrl')})")
                enriched = enrich_store_summary(data["baseUrl"], data["name"])

                if enriched:
                    data["summary"] = enriched.get("summary")
            else:
                print(f"Skipping (summary already exists): {data.get('name')}")

            # Write out each record immediately in real-time
            outfile.write(json.dumps(data) + '\n')
            outfile.flush()


if __name__ == "__main__":
    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized-enriched.jsonl"
    output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized-summary-2.jsonl"

    process_jsonl(input_path, output_path)
    print(f"Processing complete! Saved in real-time to {output_path}")