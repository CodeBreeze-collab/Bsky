import json
import os
from google import genai
from google.genai import types

# Initialize the Gemini client
# (Ensure your GEMINI_API_KEY environment variable is set)
client = genai.Client()

# Define your 7 master categories
MASTER_CATEGORIES = [
    "Apparel, Footwear & Accessories",
    "Home, Living & Outdoor",
    "Electronics, Gadgets & Tech",
    "Health, Beauty & Personal Care",
    "Pets & Animal Care",
    "Hobbies, Toys, Gifts & Collectibles",
    "Digital Products, Services & Business"
]


def categorize_store(store_name, summary, original_category, urls):
    prompt = f"""
    You are an e-commerce taxonomy expert. Your job is to assign the store below to EXACTLY ONE of the provided master categories.

    Master Categories:
    {json.dumps(MASTER_CATEGORIES, indent=2)}

    Store Details:
    - Name: {store_name}
    - Original Category: {original_category}
    - Summary: {summary}
    - Product URLs: {urls}

    You MUST output your response strictly as a JSON object with the following key:
    - "consolidated_category": the exact name of the matching master category from the list above.

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
            print(f"Warning: Empty response received for {store_name}")
            return None

        raw_text = response.text.strip()

        # Strip potential markdown formatting
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        return json.loads(raw_text.strip())
    except Exception as e:
        print(f"Error processing {store_name}: {e}")
        return None


def process_jsonl(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as infile, open(output_file, 'w', encoding='utf-8') as outfile:
        for line in infile:
            if not line.strip():
                continue
            data = json.loads(line)

            store_name = data.get("name", "Unknown")
            summary = data.get("summary", "No summary available")
            original_category = data.get("category", "Uncategorized")
            urls = data.get("product_urls", [])

            print(f"Categorizing: {store_name}...")
            categorized = categorize_store(store_name, summary, original_category, urls)

            if categorized and "consolidated_category" in categorized:
                assigned_cat = categorized["consolidated_category"]

                # Validation fallback just in case the model hallucinates a category
                if assigned_cat not in MASTER_CATEGORIES:
                    assigned_cat = "Digital Products, Services & Business"

                data["consolidated_category"] = assigned_cat
            else:
                data["consolidated_category"] = "Uncategorized"

            # Write out each record immediately in real-time
            outfile.write(json.dumps(data) + '\n')
            outfile.flush()


if __name__ == "__main__":
    # Update paths as needed based on your directory structure
    input_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/enriched_stores-w-products-filtered-final-categorized-summary-2.jsonl"
    output_path = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/goaffpro/stores-consolidated-categories.jsonl"

    process_jsonl(input_path, output_path)
    print(f"Processing complete! Saved in real-time to {output_path}")