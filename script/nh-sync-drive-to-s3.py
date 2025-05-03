import json
import os
import io
import boto3
import time
import sys
import logging
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from botocore.exceptions import ClientError



# Glue Job Args
args = sys.argv
S3_BUCKET = args[args.index("--S3_BUCKET") + 1]
CONFIG_KEY = args[args.index("--CONFIG_KEY") + 1]
SA_KEY = args[args.index("--SERVICE_ACCOUNT_KEY") + 1]
DRY_RUN = "--DRY_RUN" in args

MANIFEST_KEY = "metadata/processed_files.json"

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load Config from S3
def load_json_from_s3(s3, bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    return json.load(response["Body"])

s3 = boto3.client("s3")
CONFIG = load_json_from_s3(s3, S3_BUCKET, CONFIG_KEY)
SA_JSON = load_json_from_s3(s3, S3_BUCKET, SA_KEY)

# Google Drive Auth
creds = service_account.Credentials.from_service_account_info(
    SA_JSON,
    scopes=["https://www.googleapis.com/auth/drive"]
)
drive_service = build("drive", "v3", credentials=creds)

# Load manifest
def load_manifest():
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=MANIFEST_KEY)
        return json.load(response["Body"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return []
        raise

def update_manifest(manifest):
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=MANIFEST_KEY,
        Body=json.dumps(manifest, indent=2).encode("utf-8")
    )

# Determine path from filename
def determine_s3_path(file_name):
    normalized = file_name.replace("NH_", "").replace("_", "").lower()
    for pattern, path in CONFIG["FILE_TYPE_MAPPING"].items():
        if pattern.lower() in normalized:
            return path
    return CONFIG["FILE_TYPE_MAPPING"].get("_DEFAULT", "raw/other/")

def file_in_manifest(file_id, manifest):
    return any(item["file_id"] == file_id for item in manifest)

def retry(func, retries=3, delay=5):
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            logging.warning(f"Retry {i+1}/{retries} failed: {e}")
            time.sleep(delay)
    raise RuntimeError("Max retries exceeded")

def download_file_content(file):
    if file["mimeType"] == "application/vnd.google-apps.spreadsheet":
        request = drive_service.files().export_media(fileId=file["id"], mimeType="text/csv")
        file_name = f"{file['name']}.csv"
    else:
        request = drive_service.files().get_media(fileId=file["id"])
        file_name = file["name"]
    return file_name, request

def upload_to_s3(buffer, s3_path, file_name):
    if DRY_RUN:
        logging.info(f"[Dry Run] Would upload: {file_name}")
        return
    s3.upload_fileobj(
        Fileobj=buffer,
        Bucket=S3_BUCKET,
        Key=f"{s3_path}{file_name}",
        ExtraArgs={"ContentType": "text/csv"}
    )

def sync_drive_to_s3():
    manifest = load_manifest()
    query = f"'{CONFIG['GOOGLE_DRIVE_FOLDER_ID']}' in parents and (mimeType='text/csv' or mimeType='application/vnd.google-apps.spreadsheet')"
    files = drive_service.files().list(
        q=query,
        fields="files(id, name, mimeType, modifiedTime)",
        pageSize=1000,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute().get("files", [])

    new_manifest = list(manifest)

    for file in files:
        if file_in_manifest(file["id"], manifest):
            logging.info(f"Already synced: {file['name']}")
            continue

        file_name, content = download_file_content(file)
        s3_path = determine_s3_path(file_name)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, content)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        buffer.seek(0)

        retry(lambda: upload_to_s3(buffer, s3_path, file_name))
        logging.info(f"Uploaded: {file_name} → {s3_path}")

        new_manifest.append({
            "file_id": file["id"],
            "file_name": file_name,
            "s3_key": f"{s3_path}{file_name}",
            "synced_at": datetime.utcnow().isoformat() + "Z"
        })

    if not DRY_RUN:
        update_manifest(new_manifest)
        logging.info("Manifest updated.")

if __name__ == "__main__":
    sync_drive_to_s3()
