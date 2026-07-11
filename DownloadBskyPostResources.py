import os
import json
import re
import requests

# --- Configuration ---
JSONL_FILE_PATH = '/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/sharonantorina_bsky_social_posts_06-01-2026.jsonl'
OUTPUT_ROOT_DIR = '/Users/hdon/Desktop/bsky_images/'


def sanitize_filename(name):
    """Removes invalid characters for folder names across OS platforms."""
    return re.sub(r'[\\/*?:"<>|]', "", name)


def download_post_media():
    if not os.path.exists(JSONL_FILE_PATH):
        print(f"Error: The file {JSONL_FILE_PATH} does not exist.")
        return

    os.makedirs(OUTPUT_ROOT_DIR, exist_ok=True)
    download_count = 0
    total_lines_read = 0

    print(f"Reading file: {JSONL_FILE_PATH}...")

    with open(JSONL_FILE_PATH, 'r', encoding='utf-8') as file:
        for line in file:
            clean_line = line.strip()
            if not clean_line:
                continue  # Skip blank lines safely

            total_lines_read += 1

            try:
                post = json.loads(clean_line)
            except json.JSONDecodeError:
                print(f"⚠️ Row {total_lines_read} is not valid JSON. Skipping.")
                continue

            # Look for common variations of the key just in case
            image_urls = post.get('image_urls') or post.get('images') or []

            # If it's a string somehow, wrap it in a list
            if isinstance(image_urls, str):
                image_urls = [image_urls]

            if not image_urls:
                continue

            # Safely parse URL segments
            try:
                url_parts = post['url'].split('/')
                author = url_parts[-3]
                rkey = url_parts[-1]
            except (KeyError, IndexError):
                # Fallback parameters if URL parsing fails
                author = "unknown_user"
                rkey = f"post_{total_lines_read}"

            # Safely parse date
            date_str = post.get('date', '0000-00-00')
            date_prefix = date_str[:10]

            # Combine into a clean directory path
            folder_name = sanitize_filename(f"{date_prefix}_{author}_{rkey}")
            post_folder_path = os.path.join(OUTPUT_ROOT_DIR, folder_name)
            os.makedirs(post_folder_path, exist_ok=True)

            # 1. Save the post metadata/text
            text_file_path = os.path.join(post_folder_path, 'post_text.txt')
            with open(text_file_path, 'w', encoding='utf-8') as txt_file:
                txt_file.write(f"URL: {post.get('url', 'N/A')}\n")
                txt_file.write(f"Date: {date_str}\n")
                txt_file.write(f"Is Repost: {post.get('is_repost', False)}\n")
                txt_file.write(f"Is Reply: {post.get('is_reply', False)}\n")
                txt_file.write("-" * 40 + "\n")
                txt_file.write(post.get('text', ''))

            # 2. Download all images inside the array
            for index, img_url in enumerate(image_urls, start=1):
                try:
                    # Append conversion flag for raw CIDs on Bluesky's CDN
                    if "cdn.bsky.app/img/" in img_url and "@" not in img_url:
                        img_url = f"{img_url}@jpeg"

                    response = requests.get(img_url, stream=True, timeout=15)

                    if response.status_code == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'png' in content_type:
                            ext = 'png'
                        elif 'webp' in content_type:
                            ext = 'webp'
                        elif 'gif' in content_type:
                            ext = 'gif'
                        else:
                            ext = 'jpg'

                        img_filename = f"image_{index}.{ext}"
                        img_path = os.path.join(post_folder_path, img_filename)

                        with open(img_path, 'wb') as img_file:
                            for chunk in response.iter_content(1024):
                                img_file.write(chunk)
                    else:
                        print(f" ❌ Failed image {index} for post {rkey}: HTTP {response.status_code}")

                except Exception as e:
                    print(f" ❌ Error processing image {index} for post {rkey}: {e}")

            download_count += 1
            print(f"✓ Processed folder: {folder_name} ({len(image_urls)} images saved)")

    print(f"\n--- Execution Summary ---")
    print(f"Total rows read in file: {total_lines_read}")
    print(f"Successfully downloaded assets for: {download_count} posts.")


if __name__ == "__main__":
    download_post_media()