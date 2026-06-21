import pandas as pd
import requests
import logging
import json
import os
from io import StringIO

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def get_latest_data():
    """Fetches and cleans the current data from Google Sheets."""
    csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vToeG-avQrxn3jje7o7rgichlWwXlEaNK0T3HSPmt94p0Exav13ryEBRz9VV-YN8SQutAGCrGZzfWmM/pub?output=csv"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

    response = requests.get(csv_url, headers=headers, timeout=15)
    response.raise_for_status()

    column_names = ['name', 'animal_id', 'date', 'outcome', 'partner', 'link']
    df = pd.read_csv(StringIO(response.text), skiprows=2, names=column_names, usecols=[0, 1, 2, 3, 4, 5])

    # Scrub encoding artifacts and clean IDs
    df['animal_id'] = df['animal_id'].astype(str).str.replace('Â', '', regex=False).str.strip()
    df = df.dropna(subset=['name', 'animal_id'], how='all')
    df = df.where(pd.notnull(df), None)
    return df


def update_database(filename="nycacc_outcomes_fixed.jsonl"):
    # 1. Fetch the new data
    new_df = get_latest_data()

    # 2. Load existing data if file exists
    if os.path.exists(filename):
        logging.info(f"Loading existing data from {filename}...")
        existing_df = pd.read_json(filename, lines=True)
        # Ensure ID is string for consistent matching
        existing_df['animal_id'] = existing_df['animal_id'].astype(str)
    else:
        logging.info("No existing file found. Creating new database.")
        existing_df = pd.DataFrame(columns=new_df.columns)

    # 3. Perform the Upsert
    # We set the index to animal_id so we can update existing records easily
    existing_df.set_index('animal_id', inplace=True)
    new_df.set_index('animal_id', inplace=True)

    # update() replaces existing values with new ones where indices match
    existing_df.update(new_df)

    # combine_first() adds rows that exist in new_df but not in existing_df
    updated_df = existing_df.combine_first(new_df)

    # 4. Reset index to bring animal_id back as a column
    updated_df.reset_index(inplace=True)

    # 5. Save back to .jsonl
    updated_df.to_json(filename, orient='records', lines=True, force_ascii=False)

    new_count = len(updated_df) - len(existing_df)
    logging.info(f"Update complete. Total records: {len(updated_df)} (Added {new_count} new animals).")


if __name__ == "__main__":
    update_database()