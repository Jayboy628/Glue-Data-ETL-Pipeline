import sys
import os
import boto3
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

def move_files_between_buckets(source_bucket, processed_bucket, error_bucket, prefix, folders_to_track, dry_run=False):
    s3 = boto3.client("s3")

    prefix = prefix.rstrip("/")  # strip trailing slash if any
    source_root = f"{prefix}/raw/" if prefix else "raw/"
    logger.info(f"Scanning: s3://{source_bucket}/{source_root}")

    # Get top-level folders under raw/
    response = s3.list_objects_v2(Bucket=source_bucket, Prefix=source_root, Delimiter="/")
    common_prefixes = response.get("CommonPrefixes", [])
    logger.info(f"Found CommonPrefixes: {[p['Prefix'] for p in common_prefixes]}")

    if not common_prefixes:
        logger.warning("No folders found under raw/.")
        return

    tracked_folders = set(f.strip() for f in folders_to_track)

    total_moved = 0
    for p in common_prefixes:
        folder_prefix = p["Prefix"]
        folder_name = folder_prefix.rstrip("/").split("/")[-1]

        target_bucket = processed_bucket if folder_name in tracked_folders else error_bucket
        logger.info(f"Processing folder '{folder_name}' → Target: {target_bucket}")

        # List all files in the folder
        files = s3.list_objects_v2(Bucket=source_bucket, Prefix=folder_prefix)
        if "Contents" not in files:
            logger.warning(f"No files found in: {folder_prefix}")
            continue

        for obj in files["Contents"]:
            key = obj["Key"]
            logger.info(f"{'DRY RUN - ' if dry_run else ''}Moving {key} → s3://{target_bucket}/{key}")

            if not dry_run:
                s3.copy_object(
                    Bucket=target_bucket,
                    CopySource={"Bucket": source_bucket, "Key": key},
                    Key=key
                )
                s3.delete_object(Bucket=source_bucket, Key=key)
                total_moved += 1

    logger.info(f"Move complete. Total files moved: {total_moved}")

def parse_args():
    args = sys.argv
    get_arg = lambda flag: args[args.index(flag) + 1] if flag in args else None

    dry_run_value = get_arg("--DRY_RUN")
    dry_run = dry_run_value.lower() == "true" if dry_run_value else False

    return {
        "SOURCE_BUCKET": get_arg("--SOURCE_BUCKET"),
        "PROCESSED_BUCKET": get_arg("--PROCESSED_BUCKET"),
        "ERROR_BUCKET": get_arg("--ERROR_BUCKET"),
        "PREFIX": get_arg("--PREFIX") or "",
        "S3_FOLDERS": get_arg("--S3_FOLDERS").split(",") if get_arg("--S3_FOLDERS") else [],
        "DRY_RUN": dry_run
    }

if __name__ == "__main__":
    config = parse_args()
    logger.info(f"CONFIG: {config}")  # Log final parsed config
    move_files_between_buckets(
        source_bucket=config["SOURCE_BUCKET"],
        processed_bucket=config["PROCESSED_BUCKET"],
        error_bucket=config["ERROR_BUCKET"],
        prefix=config["PREFIX"],
        folders_to_track=config["S3_FOLDERS"],
        dry_run=config["DRY_RUN"]
    )
