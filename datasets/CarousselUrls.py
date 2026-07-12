import re
import json
import requests

BSKY_GET_POSTS = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts"
BSKY_RESOLVE_HANDLE = "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle"


def extract_handle_and_rkey(url):
    """Extracts the handle and record key (rkey) from a standard Bluesky URL."""
    match = re.search(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if match:
        return match.groups()
    return None, None


def resolve_handle_to_did(handle):
    """Resolves a human-readable handle to its internal decentralized ID (DID)."""
    try:
        resp = requests.get(BSKY_RESOLVE_HANDLE, params={"handle": handle}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("did")
    except Exception as e:
        print(f"[Error] Network issue resolving handle: {e}")
    return None


def test_carousel_extraction(url):
    print(f"Target Web URL: {url}\n")

    # 1. Split the web link components
    handle, rkey = extract_handle_and_rkey(url)
    if not handle or not rkey:
        print("❌ Invalid Bluesky URL format.")
        return
    print(f"[Step 1] Parsed handle: {handle}")
    print(f"[Step 1] Parsed rkey:   {rkey}")

    # 2. Resolve to DID
    did = resolve_handle_to_did(handle)
    if not did:
        print("❌ Handle resolution failed.")
        return
    print(f"[Step 2] Resolved DID:  {did}")

    # 3. Create the mandatory DID-based AT URI
    did_uri = f"at://{did}/app.bsky.feed.post/{rkey}"
    print(f"[Step 3] Built DID URI: {did_uri}")

    # 4. Request the post data
    print("[Step 4] Querying Bluesky AppView...")
    try:
        resp = requests.get(BSKY_GET_POSTS, params={"uris": [did_uri]}, timeout=10)
        if resp.status_code != 200:
            print(f"❌ API Error status: {resp.status_code}")
            return

        data = resp.json()
        posts = data.get("posts", [])
        if not posts:
            print("❌ API returned an empty posts list for this DID URI.")
            return

        embed = posts[0].get("embed", {})
        embed_type = embed.get("$type", "")
        print(f"[Step 4] Post found! Embed container type: {embed_type}")

        # 5. Extract images based on standalone vs nested media layouts
        image_urls = []

        # Isolate target media block whether standalone or nested inside a hybrid quote record
        media_block = embed if embed_type != "app.bsky.embed.recordWithMedia#view" else embed.get("media", {})
        actual_type = media_block.get("$type", "")

        # Branch logic to read image arrays based on active layout type
        if actual_type == "app.bsky.embed.images#view":
            images_list = media_block.get("images", [])
            print(f"[Step 5] Parsing standard image layout (up to 4 items)...")
            for img_obj in images_list:
                fullsize_url = img_obj.get("fullsize")
                if fullsize_url and fullsize_url not in image_urls:
                    image_urls.append(fullsize_url)

        elif actual_type == "app.bsky.embed.gallery#view":
            items_list = media_block.get("items", [])
            print(f"[Step 5] Parsing extended gallery carousel layout (5+ items)...")
            for img_obj in items_list:
                fullsize_url = img_obj.get("fullsize")
                if fullsize_url and fullsize_url not in image_urls:
                    image_urls.append(fullsize_url)

        if image_urls:
            print(f"\n✅ Success! Extracted {len(image_urls)} carousel images:")
            for idx, img in enumerate(image_urls, start=1):
                print(f" 👉 [{idx}]: {img}")
        else:
            print("\n⚠️ Post fetched successfully, but no matching images/gallery layout arrays were found.")

    except Exception as e:
        print(f"❌ Request execution failed: {e}")


if __name__ == "__main__":
    target_post = "https://bsky.app/profile/ckinser.bsky.social/post/3mq47sgzkzc24"
    test_carousel_extraction(target_post)