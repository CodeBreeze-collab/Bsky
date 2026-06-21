import os
import json
import time
import logging
import sys
from typing import List, Dict
from pathlib import Path
from google import genai
from google.genai import types
# Import the timeout exception from the core API package
from google.api_core.exceptions import GoogleAPICallError

# Setup logging - Added counter/progress clarity
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BlueskyAdultContentChecker:
    def __init__(self, gemini_api_key: str):
        self.client = genai.Client(
            vertexai=True,
            project="summary-334d4",
            location="us-east4"
        )
        # Using the specified 2.5 flash model
        self.model_id = "gemini-2.5-flash"
        logging.info(f"Gemini client initialized with model: {self.model_id}")

    def load_accounts(self, jsonl_path: str) -> List[Dict]:
        accounts = []
        if not os.path.exists(jsonl_path):
            logging.error(f"Input file not found: {jsonl_path}")
            return accounts
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    accounts.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return accounts

    def load_processed_dids(self, output_path: str) -> set:
        """Reads the output file to determine which DIDs are already processed."""
        processed = set()
        if not os.path.exists(output_path):
            return processed

        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    if "target_did" in data:
                        processed.add(data["target_did"])
                except Exception:
                    continue
        logging.info(f"Restart checkpoint: Found {len(processed)} already processed accounts.")
        return processed

    def call_gemini_batch(self, chunk: List[Dict], timeout_seconds: float = 45.0) -> Dict:
        """
        Submits batch to Gemini and returns a dictionary containing
        both the parsed JSON objects and the full raw text response.
        """
        simplified = []
        for acct in chunk:
            simplified.append({
                "did": acct.get("target_did"),
                "bio": acct.get("description", ""),
                "posts": (acct.get("posts", [])[:5])
            })

        prompt = (
            "You are an expert content moderator. Analyze the following list of Bluesky accounts to "
            "determine if they primarily host or promote Adult (NSFW) content. \n\n"
            "### DEFINITIONS FOR CLASSIFICATION:\n"
            "1. NSFW/ADULT (is_nsfw: true):\n"
            "   - Explicit pornography, erotic art, or sexually explicit photography.\n"
            "   - Promotion of sex work services or adult-only platforms.\n"
            "   - Accounts that self-identify as '🔞', 'NSFW', or 'Minors DNI' in the bio.\n\n"
            "2. NOT NSFW (is_nsfw: false):\n"
            "   - MEDICAL/CLINICAL: Do NOT flag professional or anatomical discussion (e.g., urology, "
            "proctology, sexual health) if the language is professional/educational.\n"
            "   - VULGARITY: Do NOT flag accounts solely for using profanity or 'toilet humor' in a "
            "political or social context (e.g., jokes about body parts).\n"
            "   - TYPOS: Ignore suggestive words that are clearly accidental typos in a non-suggestive context.\n\n"
            "### OUTPUT INSTRUCTIONS:\n"
            "Return a JSON array of objects. Each object must have:\n"
            "- 'target_did': The unique identifier provided.\n"
            "- 'is_nsfw': Boolean (true or false).\n"
            "- 'gemini_reason': A specific, one-sentence rationale.\n\n"
            f"### DATA TO ANALYZE:\n{json.dumps(simplified)}"
        )

        # Build execution configurations alongside HTTP layer parameters
        # Note: The SDK expects timeout in milliseconds (seconds * 1000)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            safety_settings=[
                types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE"
                )
            ],
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000)
            )
        )

        try:
            start_time = time.time()

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=config
            )

            latency = time.time() - start_time
            logging.info(f"API call completed in {latency:.2f} seconds.")

            raw_text = response.text if response.text else ""
            parsed_json = []

            if raw_text:
                try:
                    parsed_json = json.loads(raw_text)
                except json.JSONDecodeError:
                    logging.error("[!] Failed to parse Gemini JSON output.")

            return {
                "raw_response": raw_text,
                "parsed": parsed_json
            }

        except GoogleAPICallError as e:
            logging.error(f"[!] Gemini Batch API Call Error (likely timeout): {e}")
            return {"raw_response": f"TIMEOUT_OR_API_ERROR: {str(e)}", "parsed": []}
        except Exception as e:
            logging.error(f"[!] Gemini Batch Generic Error: {type(e).__name__}: {e}")
            return {"raw_response": f"ERROR: {str(e)}", "parsed": []}

    def process_file(self, input_path: str, output_path: str, chunk_size: int = 10):
        # 1. Guard clause: Stop immediately if the input file cannot be found
        if not os.path.exists(input_path):
            logging.error(f"[!] Processing aborted: Input file does not exist at {input_path}")
            return

        all_accounts = self.load_accounts(input_path)
        processed_dids = self.load_processed_dids(output_path)

        # 2. Filter out already processed accounts based on the output file
        todo = [a for a in all_accounts if a.get("target_did") not in processed_dids]
        total_todo = len(todo)

        if not todo:
            logging.info("[+] Everything is up to date! All accounts in the input file have already been processed.")
            return

        logging.info(f"[*] Starting processing for {total_todo} accounts...")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        total_batches = (total_todo + chunk_size - 1) // chunk_size

        # Open in append mode ("a") to preserve existing progress
        with open(output_path, "a", encoding="utf-8") as out_f:
            for i in range(0, total_todo, chunk_size):
                chunk = todo[i: i + chunk_size]
                current_batch = (i // chunk_size) + 1

                logging.info(
                    f"[*] Batch {current_batch}/{total_batches}: Sending {len(chunk)} accounts (Progress: {i}/{total_todo})..."
                )

                # Submit batch to Gemini API
                result_bundle = self.call_gemini_batch(chunk, timeout_seconds=45.0)
                raw_full_text = result_bundle["raw_response"]

                # Handle timeout scenarios gracefully
                if not result_bundle["parsed"] and "TIMEOUT" in raw_full_text:
                    logging.warning(
                        f"[-] Batch {current_batch} encountered a timeout. Recording placeholders and moving forward."
                    )

                # Map results for quick lookup within this specific chunk
                res_map = {
                    r['target_did']: r for r in result_bundle["parsed"]
                    if isinstance(r, dict) and 'target_did' in r
                }

                for item in chunk:
                    did = item.get("target_did")

                    # Match Gemini classifications back to the original accounts
                    if did in res_map:
                        item["is_nsfw"] = bool(res_map[did].get("is_nsfw", False))
                        item["gemini_reason"] = res_map[did].get("gemini_reason", "")
                    else:
                        item["is_nsfw"] = False
                        item["gemini_reason"] = "NOT_FOUND_IN_BATCH_RESPONSE_OR_TIMEOUT"

                    # Attach raw response text for compliance auditing
                    item["gemini_raw_batch_response"] = raw_full_text

                    # Write out and flush immediately to preserve progress if script drops
                    out_f.write(json.dumps(item, ensure_ascii=False) + "\n")

                out_f.flush()
                logging.info(f"[+] Flushed batch {current_batch}/{total_batches} to {output_path}")

                # Rate-limiting throttle to respect Gemini API quotas
                time.sleep(1.5)


def main():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        logging.error("GEMINI_API_KEY env variable missing.")
        return

    base_path = Path("/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets")
    input_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/block_list/nsfw_accounts/auto_follow_vse_log_tail-10000.jsonl"

    output_file = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/block_list/nsfw_accounts/vse_following_nsfw_accounts.jsonl"

    checker = BlueskyAdultContentChecker(key)
    checker.process_file(str(input_file), str(output_file), chunk_size=10)


if __name__ == "__main__":
    main()