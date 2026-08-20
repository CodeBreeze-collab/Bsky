import json
import os
from google import genai
from google.genai import types

# Initialize the Gemini client
# (Ensure your GEMINI_API_KEY environment variable is set)
client = genai.Client()


def enrich_store_data(base_url, store_name):
    prompt = f"""
    Analyze the online store named '{store_name}' with URL '{base_url}'.
    Find its main product category, write a short reasoning/description explaining what it sells, 
    and find up to 10 sample active product URLs from their website via search.

    You MUST output your response strictly as a JSON object with the following keys:
    - "product_urls": an array of strings (URLs)
    - "category": a string representing the main category
    - "reasoning": a string explaining the choice

    Do not include any markdown code blocks (like ```json) or extra text, just raw JSON.
    """

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )

        # Check if response.text is valid
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
    # Open output file once, or process line-by-line writing immediately
    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            if not line.strip():
                continue
            data = json.loads(line)

            # Only trigger API call if product_urls is missing or empty
            if not data.get("product_urls"):
                print(f"Fetching data for: {data.get('name')} ({data.get('baseUrl')})")
                enriched = enrich_store_data(data["baseUrl"], data["name"])

                if enriched:
                    data["product_urls"] = enriched.get("product_urls", [])
                    data["category"] = enriched.get("category")
                    data["reasoning"] = enriched.get("reasoning")
            else:
                print(f"Skipping (already has URLs): {data.get('name')}")

            # Write out each record immediately in real-time
            outfile.write(json.dumps(data) + '\n')
            outfile.flush()  # Forces Python to write immediately to disk


if __name__ == "__main__":
    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized.jsonl"
    output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized-enriched.jsonl"

    process_jsonl(input_path, output_path)
    print(f"Processing complete! Saved in real-time to {output_path}")