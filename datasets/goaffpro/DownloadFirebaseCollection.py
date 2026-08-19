import json
import firebase_admin
from firebase_admin import credentials, firestore


def export_collection_to_jsonl(collection_name, output_filename):
  # 1. Initialize Firebase Admin SDK
  cred = credentials.Certificate("serviceAccountKey.json")
  firebase_admin.initialize_app(cred)

  db = firestore.client()

  print(f"Fetching documents from collection '{collection_name}'...")
  docs = db.collection(collection_name).stream()

  count = 0
  with open(output_filename, "w", encoding="utf-8") as outfile:
    for doc in docs:
      doc_data = doc.to_dict()
      # Include the document ID in the exported record if desired
      doc_data["firestore_doc_id"] = doc.id

      # Write each document as a single line of JSON
      outfile.write(json.dumps(doc_data) + "\n")
      count += 1

  print(
      f"✨ Success! Exported {count} documents from '{collection_name}' to"
      f" '{output_filename}'."
  )


if __name__ == "__main__":
  # Change collection name to 'merchants' or 'stores' as needed
  target_collection = "stores"
  output_file = f"{target_collection}_export.jsonl"

  export_collection_to_jsonl(target_collection, output_file)