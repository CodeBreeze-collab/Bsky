import requests

class BlueskyDM:
    def __init__(self, handle, access_token):
        """
        handle: your Bluesky handle (e.g., user.bsky.social)
        access_token: your API access token
        """
        self.handle = handle
        self.access_token = access_token
        self.base_url = "https://bsky.social/xrpc"

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def resolve_handle_to_did(self, handle):
        """
        Resolve a user handle to their DID.
        """
        url = f"{self.base_url}/com.atproto.identity.resolveHandle"
        payload = {"handle": handle}
        response = requests.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json().get("did")

    def send_dm(self, recipient_did, message_text):
        """
        Send a direct message to a user by DID.
        """
        url = f"{self.base_url}/com.atproto.sync.createRecord"
        payload = {
            "collection": "app.bsky.dm.message",
            "repo": self.handle,
            "record": {
                "text": message_text,
                "recipient": recipient_did
            }
        }
        response = requests.post(url, json=payload, headers=self._headers())
        response.raise_for_status()
        return response.json()


def main():
    # ----- Specify your test parameters here -----
    access_token = "YOUR_ACCESS_TOKEN"
    my_handle = "yourhandle.bsky.social"
    recipient_handle = "recipienthandle.bsky.social"
    message_text = "Hello from Python!"
    # --------------------------------------------

    bsky = BlueskyDM(my_handle, access_token)
    recipient_did = bsky.resolve_handle_to_did(recipient_handle)
    print(f"Recipient DID: {recipient_did}")

    result = bsky.send_dm(recipient_did, message_text)
    print("Message sent successfully!")
    print(result)


if __name__ == "__main__":
    main()
