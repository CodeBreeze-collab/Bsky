import argparse
import os
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError


class GCSUploader:
    """
    A class to handle file uploads to Google Cloud Storage.
    """

    def __init__(self, credentials_path: str = None):
        """
        Initializes the GCS storage client.
        """
        if credentials_path:
            if os.path.exists(credentials_path):
                self.client = storage.Client.from_service_account_json(credentials_path)
            else:
                raise FileNotFoundError(f"Credentials file not found at: {credentials_path}")
        else:
            # Reverts to default environment variable (GOOGLE_APPLICATION_CREDENTIALS)
            self.client = storage.Client()

    def upload_file(self, bucket_name: str, source_file_path: str, destination_blob_name: str) -> bool:
        """
        Uploads a local file to a specified GCS bucket.
        """
        if not os.path.exists(source_file_path):
            print(f"Error: Local file '{source_file_path}' does not exist.")
            return False

        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(destination_blob_name)

            print(f"Uploading '{source_file_path}' to 'gs://{bucket_name}/{destination_blob_name}'...")
            blob.upload_from_filename(source_file_path)

            print("Success: Upload completed successfully.")
            return True

        except GoogleCloudError as gcs_err:
            print(f"Google Cloud Storage Error: {gcs_err}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False


if __name__ == "__main__":
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Upload a local file to a Google Cloud Storage bucket."
    )

    # Bucket, source, and destination are required
    parser.add_argument("-b", "--bucket", required=True, help="Name of the target GCS bucket.")
    parser.add_argument("-s", "--source", required=True, help="Local path to the file you want to upload.")
    parser.add_argument("-d", "--destination", required=True, help="The destination path/name inside the GCS bucket.")

    # Credentials path is optional if GOOGLE_APPLICATION_CREDENTIALS is set in your environment
    parser.add_argument("-c", "--credentials", help="Path to the service account JSON key file (optional).")

    args = parser.parse_args()

    try:
        # Initialize the uploader
        uploader = GCSUploader(credentials_path=args.credentials)

        # Execute the upload
        uploader.upload_file(
            bucket_name=args.bucket,
            source_file_path=args.source,
            destination_blob_name=args.destination
        )
    except Exception as err:
        print(f"Initialization Error: {err}")