# 🏥 ETL Pipeline with AWS Glue and Snowflake

This repository contains infrastructure-as-code templates and scripts to automate a full ETL pipeline that extracts nursing home data from Google Drive, transforms it using AWS Glue, and loads it into Snowflake in a star schema format.

---

## 📐 Architecture Overview

The data pipeline is orchestrated using AWS Glue workflows and consists of the following stages:

1. **Google Drive Sync** → Extract raw files to S3
2. **Universal Cleaning** → Sanitize and format CSVs into staging
3. **Source File Routing** → Move valid data to processed S3, invalid to error
4. **Validation** → Check that required staging folders contain files
5. **Transformation** → Generate warehouse-ready Parquet for Snowflake
6. **Snowflake Load** → (outside this repo) Dimensional models built in Snowflake

---

## 🧱 Infrastructure Components

### 🪣 S3 Buckets (created in `00_glue-iam-buckets.yml`)
- `nh-source-*`: Google Drive files land here (raw)
- `nh-staging-*`: Cleaned CSVs written here
- `nh-transform-*`: Transformed Parquet files ready for warehouse
- `nh-processed-*`: Processed raw files stored after validation
- `nh-error-*`: Problematic files are isolated here

### 🔐 IAM Role
A Glue-specific IAM Role with:
- `s3:*` access to all buckets matching the project prefix
- `logs:*` to enable continuous log streaming to CloudWatch

---

## 🧪 Glue Jobs (`01_glue-jobs.yml`)

| Job Name                        | Description                                                                 |
|-------------------------------|-----------------------------------------------------------------------------|
| `drive-sync`                  | Downloads raw data from Google Drive into the S3 source bucket             |
| `etl-universal-cleaning`      | Cleans and reformats raw data into the staging bucket                      |
| `move-sources-files`          | Moves valid folders to processed bucket, and invalid ones to error bucket |
| `validate-staging`            | Ensures required staging folders contain data before transformation        |
| `etl-transform`               | Reads from staging and creates Snowflake-ready data in transform bucket    |

---

## 🔄 Glue Workflow (`02_glue-workflow.yml`)

This file creates a scheduled and conditional Glue workflow that orchestrates the above jobs:

```text
Trigger:        drive-sync (Scheduled - hourly)
   ↓ on success
Trigger:        etl-universal-cleaning
   ↓ on success
Trigger:        move-sources-files
   ↓ on success
Trigger:        validate-staging
   ↓ on success
Trigger:        etl-transform
```

---

## 🔁 Scheduling

The workflow is triggered hourly using:
```bash
cron(0 * * * ? *)
```

---

## 🧰 Prerequisites

- AWS CLI configured with proper credentials
- Snowflake account and access credentials (for downstream models)
- Python 3.x
- Boto3
- Google Drive API credentials for `drive-sync` job

---

## 🚀 Deployment

To deploy the full pipeline:

```bash
# Step 1: Deploy IAM roles and S3 buckets
aws cloudformation deploy --template-file 00_glue-iam-buckets.yml --stack-name nh-glue-iam-buckets --capabilities CAPABILITY_NAMED_IAM

# Step 2: Deploy Glue jobs
aws cloudformation deploy --template-file 01_glue-jobs.yml --stack-name nh-glue-jobs --capabilities CAPABILITY_NAMED_IAM

# Step 3: Deploy Glue workflow
aws cloudformation deploy --template-file 02_glue-workflow.yml --stack-name nh-glue-workflow --capabilities CAPABILITY_NAMED_IAM
```

---

## 📊 Data Warehouse

Data output from `etl-transform` is assumed to be loaded into Snowflake where it powers the following dimensions and fact tables:

- `dim_facility`, `dim_penalties`, `dim_staffing`, etc.
- `fct_quality_mds_claims`, `fct_quality_qrp`, etc.

---

## 📂 Project Structure

```bash
cloudformation/
├── 00_glue-iam-buckets.yml       # IAM + S3 buckets
├── 01_glue-jobs.yml              # All Glue job definitions
├── 02_glue-workflow.yml          # Workflow and triggers
scripts/
├── nh-sync-drive-to-s3.py
├── nh-etl-universal-cleaning.py
├── nh-move-sources-files.py
├── nh-validate-staging.py
├── nh-etl-transform.py
```

---

## 📌 Notes

- S3 paths are dynamically templated using `${ProjectPrefix}`, `${AWS::AccountId}`, and `${Environment}`
- Logging is enabled for all jobs to CloudWatch for traceability

---

## 🧠 Future Improvements

- Add automated Snowflake ingestion from transform bucket
- Integrate dbt for model lineage and testing
- Add retry handling and file-level metadata logs

---

## 👨‍💻 Author

Built by Shaun-Jay Brown — Data Engineer | Healthcare Data Specialist

---