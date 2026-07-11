import requests
import json
import time
import re

API_KEY = "AIzaSyB--fbfQMc9IqYdJaE2MjjU7gh5sclGfyA"

STATES = [
    "Alabama", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
    "Utah", "Virginia", "Washington", "West Virginia"
]


def slugify(text):
    return re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_')


def fetch_places(query):
    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress"
    }

    payload = {
        "textQuery": query
    }

    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


def save_jsonl(filename, places_data):
    with open(filename, "w", encoding="utf-8") as f:
        for place in places_data.get("places", []):
            f.write(json.dumps(place) + "\n")


def main():
    base_query = "Crunch Fitness {}"

    for state in STATES:
        query = base_query.format(state)
        filename = f"Crunch_Fitness_{slugify(state)}.jsonl"

        print(f"Fetching: {query}")

        try:
            data = fetch_places(query)
            save_jsonl(filename, data)

            print(f"Saved → {filename} ({len(data.get('places', []))} results)")

        except Exception as e:
            print(f"Error for {state}: {e}")

        # rate limiting (important for Places API)
        time.sleep(0.5)


if __name__ == "__main__":
    main()