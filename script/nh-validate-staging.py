import boto3
import logging
import sys
from botocore.exceptions import BotoCoreError, ClientError
from awsglue.utils import getResolvedOptions  #import Glue job arguments

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def main():
    # Get job parameters from Glue's command-line args
    args = getResolvedOptions(sys.argv, ["STAGING_BUCKET", "REQUIRED_PREFIXES"])
    staging_bucket = args["STAGING_BUCKET"]
    required_prefixes = args["REQUIRED_PREFIXES"].split(",")

    logger.info(f"Validating presence of data in bucket: {staging_bucket}")
    missing_folders = []

    s3 = boto3.client("s3")

    try:
        for prefix in required_prefixes:
            folder_prefix = f"staging/{prefix.strip()}/"
            logger.info(f"Checking folder: {folder_prefix}")
            response = s3.list_objects_v2(Bucket=staging_bucket, Prefix=folder_prefix)

            keys = [obj["Key"] for obj in response.get("Contents", [])]
            logger.info(f"Found {len(keys)} file(s) in {folder_prefix}")

            if len(keys) == 0:
                logger.error(f"No files found in: {folder_prefix}")
                missing_folders.append(folder_prefix)

        if missing_folders:
            logger.error(f"Missing data in the following folders: {missing_folders}")
            sys.exit(1)
        else:
            logger.info("All required staging folders are populated.")

    except (BotoCoreError, ClientError) as e:
        logger.exception("S3 client error")
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error")
        sys.exit(1)

if __name__ == "__main__":
    main()
