import json
import math
import os
from io import BytesIO
from PIL import Image
import requests


def create_collage_from_outputs(
    input_file="/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/v2/profile_audits/adult_media_urls.jsonl",
    output_image="thumbnail_collage.jpg",
    thumb_size=(100, 100),
    columns=10,
):
    """Reads the generated JSONL file, filters out missing thumbnails,

    downloads the images, and stitches them into a grid collage.
    """
    urls = []

    # 1. Read and parse your exact JSONL structure
    if not os.path.exists(input_file):
        print(f"Error: The file {input_file} does not exist.")
        return

    print(f"Reading data from {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                url = data.get("thumbnail_url")
                handle = data.get("handle", f"User #{line_num}")

                # Ensure a thumbnail URL actually exists and isn't null/None
                if url:
                    urls.append((handle, url))
            except json.JSONDecodeError:
                print(f"Warning: Skipping malformed JSON on line {line_num}")

    if not urls:
        print("No valid thumbnail URLs found in the file.")
        return

    print(f"Found {len(urls)} thumbnails to download. Processing...")

    images = []
    # 2. Download and resize the valid images
    for handle, url in urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                img = Image.open(BytesIO(response.content))
                img = img.convert("RGB")  # Standardize color space
                img = img.resize(thumb_size)
                images.append(img)
            else:
                print(
                    f"Skipping {handle}: HTTP {response.status_code} when fetching image."
                )
        except Exception as e:
            print(f"Failed to download image for {handle}: {e}")

    if not images:
        print("No images were successfully downloaded.")
        return

    # 3. Calculate dynamic grid dimensions based on successfully downloaded images
    num_images = len(images)
    cols = columns
    rows = math.ceil(num_images / cols)

    collage_width = cols * thumb_size[0]
    collage_height = rows * thumb_size[1]

    print(f"Creating a {cols}x{rows} grid canvas...")

    # 4. Initialize canvas (using a clean white background)
    collage = Image.new("RGB", (collage_width, collage_height), color="white")

    # 5. Place each image sequentially into the grid positions
    for index, img in enumerate(images):
        col_idx = index % cols
        row_idx = index // cols

        x = col_idx * thumb_size[0]
        y = row_idx * thumb_size[1]

        collage.paste(img, (x, y))

    # 6. Save final file
    collage.save(output_image, "JPEG", quality=90)
    print(f"Success! Collage saved to {output_image}")


if __name__ == "__main__":
    # Ensure you have 'pillow' and 'requests' installed via pip
    create_collage_from_outputs()