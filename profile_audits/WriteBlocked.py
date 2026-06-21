import requests
import time

BASE = "https://bsky.social/xrpc"
PUBLIC_API = "https://public.api.bsky.app/xrpc"


class BlueskyManager:
    def __init__(self, username, app_password):
        self.username = username
        self.app_password = app_password
        self.token = None
        self.did = None

    def create_session(self):
        res = requests.post(
            f"{BASE}/com.atproto.server.createSession",
            json={"identifier": self.username, "password": self.app_password}
        )
        res.raise_for_status()
        data = res.json()
        self.token = data["accessJwt"]
        self.did = data["did"]

    def get_my_blocks(self):
        if not self.token: self.create_session()

        headers = {"Authorization": f"Bearer {self.token}"}
        cursor = None
        blocked_dids = []

        while True:
            params = {"repo": self.did, "collection": "app.bsky.graph.block", "limit": 100}
            if cursor: params["cursor"] = cursor

            res = requests.get(f"{BASE}/com.atproto.repo.listRecords", headers=headers, params=params)
            res.raise_for_status()
            data = res.json()

            for record in data.get("records", []):
                blocked_did = record.get("value", {}).get("subject")
                if blocked_did: blocked_dids.append(blocked_did)

            cursor = data.get("cursor")
            if not cursor: break
        return blocked_dids

    def get_profiles_batch(self, dids):
        """Fetches profile details in batches of 25 to respect API limits."""
        all_profiles = []
        for i in range(0, len(dids), 25):
            batch = dids[i:i + 25]
            # Use the public API for profile lookups
            res = requests.get(f"{PUBLIC_API}/app.bsky.actor.getProfiles", params={"actors": batch})
            if res.status_code == 200:
                all_profiles.extend(res.json().get("profiles", []))
            time.sleep(0.5)  # Gentle pause between batches
        return all_profiles


def main():
    USERNAME = "westcoastnews.bsky.social"
    APP_PASSWORD = "xq6i-znuq-5glk-f4rn"

    manager = BlueskyManager(USERNAME, APP_PASSWORD)

    print("Fetching blocked list...")
    dids = manager.get_my_blocks()

    print(f"Found {len(dids)} blocks. Fetching profile details...")
    profiles = manager.get_profiles_batch(dids)

    # Output results
    with open("blocked_accounts_details.csv", "w", encoding="utf-8") as f:
        f.write("Handle,Display Name,Bio,DID\n")
        for p in profiles:
            handle = p.get("handle", "")
            name = p.get("displayName", "").replace(",", " ")
            bio = p.get("description", "").replace("\n", " ").replace(",", " ")
            f.write(f"{handle},{name},{bio},{p['did']}\n")

    print("Saved 'blocked_accounts_details.csv'.")


if __name__ == "__main__":
    main()