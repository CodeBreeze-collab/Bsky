import requests
from datetime import datetime, timezone
import textwrap
import os

class BlueskyClient:
    BASE_URL = "https://bsky.social/xrpc"

    def __init__(self):
        self.handle = "pulsedigest.bsky.social" # "ethicalsearch.bsky.social" #
        self.app_password = "dwci-eynj-5eyf-fskj" # os.getenv("BLUESKY_APP_PASSWORD") #

        if not self.handle or not self.app_password:
            raise RuntimeError(
                "BLUESKY_HANDLE and BLUESKY_APP_PASSWORD must be set"
            )

        self.access_jwt = None
        self.did = None
        self._login()

    def _login(self):
        url = f"{self.BASE_URL}/com.atproto.server.createSession"
        payload = {
            "identifier": self.handle,
            "password": self.app_password,
        }

        response = requests.post(url, json=payload)
        response.raise_for_status()

        data = response.json()
        self.access_jwt = data["accessJwt"]
        self.did = data["did"]

    def post_text(self, text: str):
        url = f"{self.BASE_URL}/com.atproto.repo.createRecord"
        headers = {
            "Authorization": f"Bearer {self.access_jwt}",
            "Content-Type": "application/json",
        }

        payload = {
            "repo": self.did,
            "collection": "app.bsky.feed.post",
            "record": {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def main():
    # Define post content here (or generate it programmatically)
    post_text = dedent("""\
            Two small earthquakes shook Southern New England Wednesday: a 1.9 magnitude near Moodus, CT, and a 1.8 near Mattapoisett, MA. East Coast quakes are rare but can be felt over wider areas.

            #Earthquake #NewEngland #USGS #CT #MA

            https://www.wpri.com/community/environment/2-earthquakes-recorded-in-southern-new-england/
        """).strip()

    print(len(post_text))

    MAX_CHARS = 300

    if len(post_text) > MAX_CHARS:
        raise ValueError(
            f"Post too long: {len(post_text)} characters (max {MAX_CHARS})"
        )

    print(post_text)

    client = BlueskyClient()
    result = client.post_text(post_text)

    print("Post created successfully!")
    print("URI:", result["uri"])


if __name__ == "__main__":
    main()
