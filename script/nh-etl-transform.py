"""
Combined ETL script for 'provider_info' and 'qualitymsr_mds' domains with schema enforcement
"""
import sys
from datetime import datetime
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from awsglue.job import Job
from pyspark.sql.functions import col, monotonically_increasing_id, current_date
from pyspark.sql.types import *

# Parse arguments
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'STAGING_PATH',
    'TRANSFORM_PATH',
    'DOMAIN',
    'ERROR_PATH'
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Helper to apply schema
def cast_columns(df, schema_dict):
    for col_name, dtype in schema_dict.items():
        if col_name in df.columns:
            df = df.withColumn(col_name, col(col_name).cast(dtype))
    return df

# Schemas
facility_schema = {
    "facility_number": StringType(),
    "facility_address": StringType(),
    "city_town": StringType(),
    "state": StringType(),
    "zip_code": StringType(),
    "telephone_number": StringType(),
    "ownership_type": StringType(),
    "number_of_certified_beds": IntegerType(),
    "average_number_of_residents_per_day": DoubleType(),
    "average_number_of_residents_per_day_footnote": DateType(),
    "facility_type": StringType(),
    "provider_resides_in_hospital": StringType(),
    "legal_business_name": StringType(),
    "date_first_approved_to_provide_medicare_and_medicaid_services": DateType(),
    "affiliated_entity_name": StringType(),
    "affiliated_entity_id": StringType(),
    "continuing_care_retirement_community": StringType(),
    "special_focus_status": DateType(),
    "abuse_icon": StringType(),
    "row_id": LongType(),
    "etl_date": DateType()
}

quality_schema = {
    "facility_number": StringType(),
    "measure_code": StringType(),
    "measure_description": StringType(),
    "resident_type": StringType(),
    "q1_measure_score": DoubleType(),
    "footnote_for_q1_measure_score": StringType(),
    "q2_measure_score": DoubleType(),
    "footnote_for_q2_measure_score": StringType(),
    "q3_measure_score": DoubleType(),
    "footnote_for_q3_measure_score": StringType(),
    "q4_measure_score": DoubleType(),
    "footnote_for_q4_measure_score": StringType(),
    "four_quarter_average_score": DoubleType(),
    "footnote_for_four_quarter_average_score": DateType(),
    "used_in_quality_measure_five_star_rating": StringType(),
    "measure_period": StringType(),
    "location": StringType(),
    "processing_date": DateType(),
    "row_id": LongType(),
    "etl_date": DateType()
}

# Drop columns reused across domains
drop_cols = ['facility_name', 'facility_address', 'city_town', 'zip_code']

# Domain logic
if args['DOMAIN'] == 'provider':
    df = spark.read.parquet(f"{args['STAGING_PATH']}provider_info/")
    df = cast_columns(df, facility_schema)

    df_facility = df.select(*facility_schema.keys())
    df_facility.write.mode("overwrite").parquet(f"{args['TRANSFORM_PATH']}facility/")

    df_staffing = df.select([c for c in df.columns if any(k in c for k in [
        "facility_number", "staffing", "hours_per", "turnover", "case_mix", "adjusted"
    ])])

    df_rating = df.select([c for c in df.columns if "rating" in c or "footnote" in c or "facility_number" in c])

    df_surveys = df.select([c for c in df.columns if any(k in c for k in [
        "rating_cycle", "health_deficiency", "revisit_score", "total_weighted_health_survey_score", "facility_number"
    ])])

    df_survey_summary = spark.read.parquet(f"{args['STAGING_PATH']}survey_summary/")
    df_survey_summary = df_survey_summary.drop(*[c for c in drop_cols if c in df_survey_summary.columns])
    df_survey_summary = df_survey_summary.withColumnRenamed("facility_number", "facility_number")
    df_surveys_joined = df_surveys.join(df_survey_summary, on="facility_number", how="left")

    df_penalties = df.select(
        "facility_number", "number_of_facility_reported_incidents",
        "number_of_substantiated_complaints", "number_of_citations_from_infection_control_inspections",
        "number_of_fines", "total_amount_of_fines_in_dollars",
        "number_of_payment_denials", "total_number_of_penalties"
    )
    df_penalties_ext = spark.read.parquet(f"{args['STAGING_PATH']}penalties/")
    df_penalties_ext = df_penalties_ext.drop(*[c for c in drop_cols if c in df_penalties_ext.columns])
    df_penalties_joined = df_penalties.join(df_penalties_ext, on="facility_number", how="left")

    output_frames = {
        "staffing": df_staffing,
        "rating": df_rating,
        "surveys": df_surveys_joined,
        "penalties": df_penalties_joined
    }

    for name, frame in output_frames.items():
        frame = frame.withColumn("row_id", monotonically_increasing_id())
        frame = frame.withColumn("etl_date", current_date())
        frame.write.mode("overwrite").parquet(f"{args['TRANSFORM_PATH']}{name}/")

elif args['DOMAIN'] == 'qualitymsr':
    try:
        df = spark.read.parquet(f"{args['STAGING_PATH']}qualitymsr_mds/")
        df = cast_columns(df, quality_schema)

        df = df.withColumn("row_id", monotonically_increasing_id().cast(LongType()))
        df = df.withColumn("etl_date", current_date().cast(DateType()))
        df.write.mode("overwrite").parquet(f"{args['TRANSFORM_PATH']}qualitymsr_mds/")
    except Exception as e:
        print(f"Error: {e}")
        if 'df' in locals():
            df.write.mode("overwrite").parquet(f"{args['ERROR_PATH']}qualitymsr_mds/")
else:
    raise ValueError("Invalid DOMAIN. Use 'provider' or 'qualitymsr'")

job.commit()
