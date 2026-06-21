import argparse
import json
import re
import sys


def extract_emails_from_json(file_path):
    """Parses a SerpApi JSON file and extracts unique email addresses."""
    # Regular expression pattern to find email addresses
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

    # Use a set to prevent duplicate email entries
    extracted_emails = set()

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Navigate safely to the organic results array
        organic_results = data.get("organic_results", [])

        if not organic_results:
            print("Warning: No 'organic_results' found in the JSON data.")

        for result in organic_results:
            # Check all fields where an email might hide (title, snippet, or link)
            text_to_search = f"{result.get('title', '')} {result.get('snippet', '')} {result.get('link', '')}"

            # Find all matches in the combined text string
            matches = re.findall(email_pattern, text_to_search)

            # Clean and add found emails to our set
            for email in matches:
                extracted_emails.add(email.strip().lower())

        # Display results
        if extracted_emails:
            print(f"--- Found {len(extracted_emails)} unique email(s) ---")
            for email in sorted(extracted_emails):
                print(f"- {email}")
        else:
            print("No email addresses were found in the organic results.")

    except FileNotFoundError:
        print(
            f"Error: The file '{file_path}' was not found. Please verify the path.",
            file=sys.stderr,
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print(
            "Error: Failed to decode JSON. Check if the file is formatted correctly.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    """Sets up command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Extract email addresses from a SerpApi JSON results file."
    )

    # Positional argument for the file path
    parser.add_argument(
        "file_path", help="Path to the .json file you want to process"
    )

    args = parser.parse_args()

    # Call the extraction function with the provided argument
    extract_emails_from_json(args.file_path)


if __name__ == "__main__":
    main()