import json
import os
import requests
import time
from datetime import datetime, timezone
from typing import Dict


class BlueskyHandleAuditor:
    # --- CLASS CONSTANTS ---
    # Change this to your actual full path (e.g., "C:/Users/Name/Desktop/auto_follow_log.jsonl")
    DEFAULT_LOG_PATH = "auto_follow_log.jsonl"

    def __init__(self, operator_handle: str, operator_pwd: str, log_file: str = None):
        self.handle = operator_handle
        self.password = operator_pwd

        # Use provided log_file, or fall back to the class constant
        target_path = log_file if log_file else self.DEFAULT_LOG_PATH

        # Expand user (~) and get the absolute path to prevent location errors
        self.log_file = os.path.abspath(os.path.expanduser(target_path))

        self.token = None
        self.history: Dict[str, datetime] = self._load_history_by_handle()

    def _normalize(self, handle: str) -> str:
        if not handle: return ""
        return handle.strip().lower().lstrip('@')

    def _load_history_by_handle(self) -> Dict[str, datetime]:
        history = {}

        # Debugging: Print exactly where the script is looking
        print(f"🔍 Looking for log file at: {self.log_file}")

        if not os.path.exists(self.log_file):
            print(f"❌ ERROR: File not found at the path above.")
            return history

        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    raw_handle = data.get("target_handle")
                    ts_str = data.get("timestamp")

                    if raw_handle and ts_str:
                        clean_handle = self._normalize(raw_handle)
                        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        if clean_handle not in history:
                            history[clean_handle] = dt
                except Exception:
                    continue

        print(f"📖 Log Audit: Loaded {len(history)} unique handles.")
        return history

    def _get_session(self):
        url = "https://bsky.social/xrpc/com.atproto.server.createSession"
        res = requests.post(url, json={"identifier": self.handle, "password": self.password})
        res.raise_for_status()
        self.token = res.json()["accessJwt"]

    def _fetch_all_handles(self, endpoint: str, actor_did: str, key: str) -> set:
        headers = {"Authorization": f"Bearer {self.token}"}
        handles = set()
        cursor = None
        while True:
            params = {"actor": actor_did, "limit": 100}
            if cursor: params["cursor"] = cursor
            res = requests.get(f"https://bsky.social/xrpc/{endpoint}", headers=headers, params=params)
            data = res.json()
            for item in data.get(key, []):
                handles.add(self._normalize(item["handle"]))
            cursor = data.get("cursor")
            if not cursor: break
            time.sleep(0.3)
        return handles

    def audit_target(self, target_handle: str):
        self._get_session()

        res = requests.get("https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
                           params={"handle": target_handle})
        target_did = res.json().get("did")

        following = self._fetch_all_handles("app.bsky.graph.getFollows", target_did, "follows")
        followers = self._fetch_all_handles("app.bsky.graph.getFollowers", target_did, "followers")

        unrequited = following - followers
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_filename = f"unrecognized_{run_ts}.txt"
        now = datetime.now(timezone.utc)

        print(f"\nAudit Results for @{target_handle}:")
        print("-" * 60)

        with open(txt_filename, "w", encoding="utf-8") as f:
            for handle in sorted(unrequited):
                if handle in self.history:
                    follow_date = self.history[handle]
                    days = (now - follow_date).days
                    print(f"@{handle:<30} | YES ✅ ({days}d)")
                else:
                    print(f"@{handle:<30} | NO ❌ (Exported)")
                    f.write(f"@{handle}\n")
                    f.flush()

        print(f"\n✅ Audit complete. Results saved to {txt_filename}")


# --- Execution ---
if __name__ == "__main__":
    # You can now put the absolute path here:
    FULL_PATH_TO_LOG = "/Users/hdon/Projects/Firebase/real-time/bsky-firehose/python/bsky/auto_follow_log.jsonl"

    MY_HANDLE = "ethicalsearch.bsky.social"
    MY_PWD = os.environ.get("BLUESKY_APP_PASSWORD")
    TARGET = "vegansearchengine.bsky.social"

    # Option A: Uses the Class Constant DEFAULT_LOG_PATH
    auditor = BlueskyHandleAuditor(MY_HANDLE, MY_PWD)

    # Option B: Overrides with a specific path
    # auditor = BlueskyHandleAuditor(MY_HANDLE, MY_PWD, log_file=FULL_PATH_TO_LOG)

    auditor.audit_target(TARGET)