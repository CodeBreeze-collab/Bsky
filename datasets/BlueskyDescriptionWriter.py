import os
import json
import logging
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyAugmentDescriptions:
    def __init__(self, input_file: str, output_file: str):
        self.input_file = input_file
        self.output_file = output_file

    def load_accounts(self) -> List[Dict]:
        """Load accounts from the input JSONL file."""
        accounts = []
        if not os.path.exists(self.input_file):
            logging.warning(f"Input file {self.input_file} not found.")
            return accounts

        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    accounts.append(json.loads(line))
                except Exception as e:
                    logging.warning(f"Skipping invalid line: {e}")
        logging.info(f"Loaded {len(accounts)} accounts from {self.input_file}")
        return accounts

    def load_already_written(self) -> set:
        """Load already processed handles from the output file for restart safety."""
        processed = set()
        if os.path.exists(self.output_file):
            with open(self.output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        processed.add(record.get("handle"))
                    except Exception:
                        continue
        logging.info(f"{len(processed)} handles already written to {self.output_file}")
        return processed

    def augment_and_write(self, accounts: List[Dict]):
        """Add description and image_url fields while preserving original fields."""
        processed_handles = self.load_already_written()
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        count_written = 0

        with open(self.output_file, 'a', encoding='utf-8') as f_out:
            for acct in accounts:
                handle = acct.get("handle")
                if not handle or handle in processed_handles:
                    continue

                # Preserve all existing fields
                acct["description"] = acct.get("description") or ""

                # Correctly pick image URL from known possible keys
                image_url = acct.get("avatar") or acct.get("profile_image_url") or ""
                if not image_url:
                    logging.debug(f"No image URL found for {handle}")
                acct["image_url"] = image_url

                f_out.write(json.dumps(acct, ensure_ascii=False) + "\n")
                processed_handles.add(handle)
                count_written += 1

        logging.info(f"Wrote {count_written} new records with descriptions to {self.output_file}")


if __name__ == "__main__":
    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts_active.jsonl"
    output_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/bluesky_rescue_accounts_w_descriptions.jsonl"

    augmenter = BlueskyAugmentDescriptions(input_file, output_file)
    accounts = augmenter.load_accounts()
    augmenter.augment_and_write(accounts)