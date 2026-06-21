from atproto import Client

HANDLE = "ethicalsearch.bsky.social"
APP_PASSWORD = "bilm-gvql-5toq-d434"


def fetch_all_posts(query, max_pages=3):
    client = Client()
    client.login(HANDLE, APP_PASSWORD)

    all_posts = []
    cursor = None  # Start with no cursor for the first page
    pages_fetched = 0

    print(f"Searching for: {query}")

    while pages_fetched < max_pages:
        # Fetch a page of results
        params = {'q': query, 'limit': 50, 'cursor': cursor}
        response = client.app.bsky.feed.search_posts(params=params)

        # Add found posts to our list
        all_posts.extend(response.posts)
        pages_fetched += 1
        print(f"Fetched page {pages_fetched} ({len(response.posts)} posts found)")

        # Update the cursor for the next iteration
        cursor = response.cursor

        # If there's no cursor, we've reached the end of the results
        if not cursor:
            print("No more results available.")
            break

    return all_posts


# Example Usage
results = fetch_all_posts("dog", max_pages=5)
for p in results:
    print(f"@{p.author.handle}: {p.record.text}")