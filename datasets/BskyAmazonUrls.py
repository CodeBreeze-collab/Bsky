import os
import json
import re
from datetime import datetime
import requests

# Read from your corrected dataset path
INPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_6"
# Output to a new version directory
OUTPUT_DIR = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/datasets/needs_help_v2_/v3_corrected/video_enriched_w_urls_2"

BSKY_BASE_URL = "https://public.api.bsky.app/xrpc"

# In-memory cache to prevent redundant API network trips for duplicate URLs
API_URL_CACHE = {}


def parse_date_dir(dirname):
    try:
        return datetime.strptime(dirname, "%m-%d-%Y")
    except ValueError:
        return None


def get_sorted_date_dirs(input_dir):
    dirs = []
    if not os.path.exists(input_dir):
        return dirs
    for name in os.listdir(input_dir):
        path = os.path.join(input_dir, name)
        if os.path.isdir(path):
            dt = parse_date_dir(name)
            if dt:
                dirs.append((dt, path))
    dirs.sort(key=lambda x: x[0], reverse=True)
    return dirs


def collect_text(obj):
    """Recursively collect all human-readable text fields."""
    texts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                texts.append(v)
            else:
                texts.extend(collect_text(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(collect_text(item))
    return texts


def check_for_pledges(text):
    text_lower = text.lower()
    return "pledge" in text_lower or "$" in text_lower or "dollar" in text_lower


def _resolve_handle_to_did(handle: str) -> str:
    try:
        endpoint = f"{BSKY_BASE_URL}/com.atproto.identity.resolveHandle"
        resp = requests.get(endpoint, params={"handle": handle}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("did")
    except Exception:
        pass
    return None


def _normalize_to_at_uri(url: str) -> str:
    match = re.search(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if not match:
        return None
    handle_or_did, rkey = match.groups()
    if not handle_or_did.startswith("did:"):
        did = _resolve_handle_to_did(handle_or_did)
        if not did:
            return None
    else:
        did = handle_or_did
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def fetch_true_untruncated_urls(post_url: str) -> list:
    """Queries the Bluesky AppView live to pull the authentic full links out of the post facets/embeds."""
    if not post_url:
        return []

    if post_url in API_URL_CACHE:
        return API_URL_CACHE[post_url]

    found_urls = []
    try:
        at_uri = _normalize_to_at_uri(post_url)
        if not at_uri:
            return []

        endpoint = f"{BSKY_BASE_URL}/app.bsky.feed.getPosts"
        resp = requests.get(endpoint, params={"uris": [at_uri]}, timeout=8)

        if resp.status_code == 200:
            data = resp.json()
            posts = data.get("posts", [])
            if posts:
                post = posts[0]
                record = post.get("record", {})

                # 1. Pull from rich-text anchor facets
                facets = record.get("facets", [])
                for facet in facets:
                    for feature in facet.get("features", []):
                        if feature.get("$type") == "app.bsky.richtext.facet#link":
                            uri = feature.get("uri")
                            if uri and uri not in found_urls:
                                found_urls.append(uri)

                # 2. Pull from external link preview cards
                embed = post.get("embed", {})
                if embed.get("$type") == "app.bsky.embed.external#view":
                    external_uri = embed.get("external", {}).get("uri")
                    if external_uri and external_uri not in found_urls:
                        found_urls.append(external_uri)

    except Exception as e:
        print(f"      [Warning] Could not resolve live links for {post_url}: {e}")

    # Cache results (even if empty, to safeguard against broken/deleted post lookup loops)
    API_URL_CACHE[post_url] = found_urls
    return found_urls


def process_file(input_file, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    processed = 0
    pledge_count = 0

    with open(input_file, "r", encoding="utf-8") as infile, \
            open(output_file, "w", encoding="utf-8") as outfile:

        for line in infile:
            if not line.strip():
                continue

            record = json.loads(line)

            # Flatten text components for the pledge flag processor
            combined_text = "\n".join(collect_text(record))
            has_pledge = check_for_pledges(combined_text)
            record["has_pledge"] = has_pledge

            if has_pledge:
                pledge_count += 1

            # Target the post source URL to resolve the full destination addresses
            target_url = record.get("post_url")
            if not target_url and record.get("associated_posts"):
                target_url = record["associated_posts"][0].get("post_url")

            if target_url:
                # Live extract the true, un-truncated links
                record["internal_urls"] = fetch_true_untruncated_urls(target_url)
            else:
                record["internal_urls"] = []

            outfile.write(json.dumps(record, ensure_ascii=False) + "\n")
            processed += 1

    print(f"   Done: processed={processed}, found {pledge_count} posts with pledges.")


def main():
    date_dirs = get_sorted_date_dirs(INPUT_DIR)
    if not date_dirs:
        print(f"No date directories found in {INPUT_DIR}")
        return

    for dt, date_dir in date_dirs:
        print(f"\nProcessing date directory: {dt.strftime('%m-%d-%Y')}")

        for root, _, files in os.walk(date_dir):
            for filename in files:
                if filename != "animal_centric_posts-w-loc-2.jsonl":
                    continue

                input_file = os.path.join(root, filename)
                relative = os.path.relpath(root, INPUT_DIR)
                output_file = os.path.join(OUTPUT_DIR, relative, filename)

                print(f"   {input_file}")
                process_file(input_file, output_file)


if __name__ == "__main__":
    main()