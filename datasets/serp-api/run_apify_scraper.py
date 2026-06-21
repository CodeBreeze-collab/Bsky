import argparse
import json
import sys
from apify_client import ApifyClient


def run_instagram_scraper(api_token, keywords, domains, output_file):
    """Initializes the Apify client, runs the Instagram email scraper actor,

    and saves the dataset results locally.
    """
    # Initialize the client with your personal API token
    client = ApifyClient(api_token)

    # Configure the inputs expected by the scraper-mind/instagram-email-scraper Actor
    actor_input = {
        "keywords": keywords,  # This should be a list of search strings
        "domains": domains,  # List of target email domains
        "proxyConfig": {"useApifyProxy": True},  # Highly recommended to avoid blocks
        # You can add additional fields here if the actor supports them (e.g., "limit": 100)
    }

    print("Submitting task to Apify cloud...")
    print(f"Keywords: {keywords}")
    print(f"Target Domains: {domains}")

    try:
        # Call the actor synchronously using .call().
        # This will block execution until the scraper completes its run in the cloud.
        run = client.actor("scraper-mind/instagram-email-scraper").call(
            run_input=actor_input
        )

        # Check if the run finished successfully
        if run.get("status") != "SUCCEEDED":
            print(
                f"Actor completed with unexpected status: {run.get('status')}",
                file=sys.stderr,
            )
            return

        print(
            f"Scraper run finished successfully! Run ID: {run.get('id')}"
        )
        print("Fetching extracted data from the Apify Dataset storage...")

        # Get the dataset ID associated with this run
        dataset_id = run.get("defaultDatasetId")

        # Fetch all results inside the dataset container
        dataset_items = client.dataset(dataset_id).list_items().items

        print(
            f"Successfully retrieved {len(dataset_items)} total entries from the cloud."
        )

        # Write the data out to a local JSON file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dataset_items, f, indent=2, ensure_ascii=False)

        print(f"Data has been saved locally to: '{output_file}'")

    except Exception as e:
        print(
            f"An error occurred while communicating with Apify: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Trigger the scraper-mind/instagram-email-scraper Actor via Python."
    )

    # Required API Key
    parser.add_argument(
        "--token", required=True, help="Your personal Apify API Token."
    )

    # Output file configuration
    parser.add_argument(
        "--output",
        default="apify_instagram_emails.json",
        help="Path to save the resulting JSON data (default: apify_instagram_emails.json).",
    )

    args = parser.parse_args()

    # Define the criteria matches you want the cloud actor to query
    target_keywords = ["exploitation"]
    target_domains = ["gmail.com", "hotmail.com", "outlook.com"]

    # Execute the workflow
    run_instagram_scraper(
        api_token=args.token,
        keywords=target_keywords,
        domains=target_domains,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()