import argparse
import json
import sys
from serpapi import Client


def fetch_all_pages(api_key, query, max_pages=5):
    """Queries SerpApi for a given query, handles pagination,

    and returns a combined list of organic results and full metadata.
    """
    # Initialize the SerpApi Client
    client = Client(api_key=api_key)

    all_organic_results = []
    current_start = 0

    print(f"Starting search for: '{query}'")

    for page in range(1, max_pages + 1):
        print(f"Fetching page {page} (starting index: {current_start})...")

        # Set up the search parameters
        params = {
            "engine": "google",
            "q": query,
            "num": 100,  # Request 100 results per page to maximize credit value
            "start": current_start,
        }

        try:
            # Execute the search
            results = client.search(params)
        except Exception as e:
            print(f"An error occurred while fetching data: {e}", file=sys.stderr)
            break

        # Extract organic search results from the response
        organic_batch = results.get("organic_results", [])
        if not organic_batch:
            print("No more organic results found. Ending pagination.")
            break

        print(f"Found {len(organic_batch)} results on this page.")
        all_organic_results.extend(organic_batch)

        # Check if SerpApi indicates there is a next page available
        pagination_info = results.get("serpapi_pagination", {})
        if "next" not in pagination_info:
            print("Reached the final page of available results.")
            break

        # Increment the start index by 100 for the next page loop
        current_start += 100

    print(f"Total organic results gathered across all pages: {len(all_organic_results)}")

    # Return a structured dictionary mapping closely to the standard format
    return {"query": query, "organic_results": all_organic_results}


def main():
    parser = argparse.ArgumentParser(
        description="Paginate SerpApi Google search results and save to JSON."
    )
    parser.add_argument(
        "--api_key",
        required=True,
        help="Your SerpApi private API key.",
    )
    parser.add_argument(
        "--output",
        default="paginated_results.json",
        help="Path to save the output JSON file (default: paginated_results.json).",
    )
    parser.add_argument(
        "--max_pages",
        type=int,
        default=5,
        help="Maximum number of pages to pull (default: 5 pages / ~500 results).",
    )

    args = parser.parse_args()

    # The exact query string you want to target
    target_query = (
        "site:instagram.com (exploitation) (@gmail.com OR @hotmail.com OR @outlook.com)"
    )

    # Run the pagination loop
    combined_data = fetch_all_pages(
        api_key=args.api_key, query=target_query, max_pages=args.max_pages
    )

    # Save to JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)

    print(f"Success! Complete dataset saved to '{args.output}'")


if __name__ == "__main__":
    main()