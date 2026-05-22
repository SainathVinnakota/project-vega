# adapters/aws/bedrock_kb_manager.py
"""Dynamic Bedrock Knowledge Base lifecycle management via boto3."""

import uuid
import structlog
import boto3
from botocore.exceptions import ClientError

logger = structlog.get_logger(__name__)


class BedrockKBManager:
    """Create, sync, query status, and delete Bedrock Knowledge Bases programmatically."""

    def __init__(
        self,
        region: str = "us-east-1",
        role_arn: str = "",
        embedding_model_arn: str = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
    ):
        self.region = region
        self.role_arn = role_arn
        self.embedding_model_arn = embedding_model_arn
        self.client = boto3.client("bedrock-agent", region_name=region)
        self._rds_resource_arn = ""
        self._rds_credentials_secret_arn = ""
        logger.info("bedrock_kb_manager_initialized", region=region)

    def create_knowledge_base(
        self,
        name: str,
        description: str,
        rds_resource_arn: str,
        rds_credentials_secret_arn: str,
        rds_database_name: str = "postgres",
        rds_table_name: str = "bedrock_integration.bedrock_kb",
    ) -> dict:
        """Create a new Bedrock Knowledge Base backed by Aurora PostgreSQL (pgvector)."""
        try:
            response = self.client.create_knowledge_base(
                clientToken=str(uuid.uuid4()),
                name=name,
                description=description,
                roleArn=self.role_arn,
                knowledgeBaseConfiguration={
                    "type": "VECTOR",
                    "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": self.embedding_model_arn,
                    },
                },
                storageConfiguration={
                    "type": "RDS",
                    "rdsConfiguration": {
                        "resourceArn": rds_resource_arn,
                        "credentialsSecretArn": rds_credentials_secret_arn,
                        "databaseName": rds_database_name,
                        "tableName": rds_table_name,
                        "fieldMapping": {
                            "primaryKeyField": "id",
                            "vectorField": "embedding",
                            "textField": "chunks",
                            "metadataField": "metadata",
                        },
                    },
                },
            )
            kb = response["knowledgeBase"]
            logger.info("kb_created", kb_id=kb["knowledgeBaseId"], name=name, status=kb["status"])
            return kb
        except ClientError as e:
            logger.error("kb_creation_failed", name=name, error=str(e))
            raise

    def add_s3_data_source(
        self,
        kb_id: str,
        s3_bucket: str,
        s3_prefix: str = "",
        data_source_name: str | None = None,
        chunking_strategy: str = "SEMANTIC",
        chunk_size: int = 300,
        chunk_overlap: int = 20,
        parsing_strategy: str | None = None,
        parsing_model_arn: str | None = None,
    ) -> dict:
        """Add an S3 folder as a data source to an existing Knowledge Base.

        Args:
            kb_id: Knowledge Base ID.
            s3_bucket: S3 bucket name.
            s3_prefix: S3 key prefix (folder).
            data_source_name: Custom name for the data source.
            chunking_strategy: One of NONE, FIXED_SIZE, SEMANTIC, HIERARCHICAL.
                               Default: SEMANTIC (best for mixed-format documents).
            chunk_size: Max tokens per chunk (used with FIXED_SIZE). Default: 300.
            chunk_overlap: Overlap percentage between chunks (used with FIXED_SIZE). Default: 20.
            parsing_strategy: None (standard parser) or BEDROCK_FOUNDATION_MODEL
                              (FM-based parsing for complex layouts in Word/PDF).
            parsing_model_arn: Foundation model ARN for FM parsing. Required if
                               parsing_strategy is BEDROCK_FOUNDATION_MODEL.
                               Example: arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-sonnet-20240229-v1:0
        """
        ds_name = data_source_name or f"{s3_bucket}-{s3_prefix.strip('/')}"
        try:
            s3_config: dict = {"bucketArn": f"arn:aws:s3:::{s3_bucket}"}
            if s3_prefix:
                s3_config["inclusionPrefixes"] = [s3_prefix]

            # Build vectorIngestionConfiguration
            ingestion_config: dict = {}

            # Chunking configuration
            chunking_strategy = chunking_strategy.upper()
            if chunking_strategy == "NONE":
                ingestion_config["chunkingConfiguration"] = {"chunkingStrategy": "NONE"}
            elif chunking_strategy == "FIXED_SIZE":
                ingestion_config["chunkingConfiguration"] = {
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": chunk_size,
                        "overlapPercentage": chunk_overlap,
                    },
                }
            elif chunking_strategy == "SEMANTIC":
                ingestion_config["chunkingConfiguration"] = {
                    "chunkingStrategy": "SEMANTIC",
                    "semanticChunkingConfiguration": {
                        "maxTokens": chunk_size,
                        "bufferSize": 0,
                        "breakpointPercentileThreshold": 95,
                    },
                }
            elif chunking_strategy == "HIERARCHICAL":
                ingestion_config["chunkingConfiguration"] = {
                    "chunkingStrategy": "HIERARCHICAL",
                    "hierarchicalChunkingConfiguration": {
                        "levelConfigurations": [
                            {"maxTokens": chunk_size * 4},  # parent chunk
                            {"maxTokens": chunk_size},  # child chunk
                        ],
                        "overlapTokens": chunk_overlap,
                    },
                }
            else:
                logger.warning("unknown_chunking_strategy", strategy=chunking_strategy)

            # Parsing configuration (for complex documents like Word/PDF)
            if parsing_strategy == "BEDROCK_FOUNDATION_MODEL":
                model_arn = parsing_model_arn or (
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-pro-v1:0"
                )
                ingestion_config["parsingConfiguration"] = {
                    "parsingStrategy": "BEDROCK_FOUNDATION_MODEL",
                    "bedrockFoundationModelConfiguration": {
                        "modelArn": model_arn,
                    },
                }

            # Build create_data_source kwargs
            create_kwargs: dict = {
                "knowledgeBaseId": kb_id,
                "clientToken": str(uuid.uuid4()),
                "name": ds_name,
                "dataSourceConfiguration": {
                    "type": "S3",
                    "s3Configuration": s3_config,
                },
            }
            if ingestion_config:
                create_kwargs["vectorIngestionConfiguration"] = ingestion_config

            response = self.client.create_data_source(**create_kwargs)
            ds = response["dataSource"]
            logger.info(
                "data_source_added",
                kb_id=kb_id,
                ds_id=ds["dataSourceId"],
                bucket=s3_bucket,
                chunking=chunking_strategy,
                parsing=parsing_strategy or "STANDARD",
            )
            return ds
        except ClientError as e:
            logger.error("data_source_add_failed", kb_id=kb_id, error=str(e))
            raise

    def sync_data_source(self, kb_id: str, data_source_id: str) -> dict:
        """Trigger an ingestion job to sync S3 data into the vector store."""
        try:
            response = self.client.start_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=data_source_id,
            )
            job = response["ingestionJob"]
            logger.info(
                "ingestion_started", kb_id=kb_id, ds_id=data_source_id, job_id=job["ingestionJobId"]
            )
            return job
        except ClientError as e:
            logger.error("ingestion_start_failed", kb_id=kb_id, error=str(e))
            raise

    def get_kb_status(self, kb_id: str) -> dict:
        """Get the current status and details of a Knowledge Base."""
        try:
            response = self.client.get_knowledge_base(knowledgeBaseId=kb_id)
            return response["knowledgeBase"]
        except ClientError as e:
            logger.error("kb_status_check_failed", kb_id=kb_id, error=str(e))
            raise

    def list_knowledge_bases(self) -> list[dict]:
        """List all Knowledge Bases in the account/region."""
        try:
            response = self.client.list_knowledge_bases(maxResults=100)
            return response.get("knowledgeBaseSummaries", [])
        except ClientError as e:
            logger.error("kb_list_failed", error=str(e))
            raise

    def get_kb_id_by_name(self, name: str) -> str | None:
        """Find a Knowledge Base ID by its name."""
        try:
            for kb in self.list_knowledge_bases():
                if kb.get("name") == name:
                    return kb.get("knowledgeBaseId")
            return None
        except Exception:
            return None

    def list_data_sources(self, kb_id: str) -> list[dict]:
        """List all data sources for a Knowledge Base."""
        try:
            response = self.client.list_data_sources(knowledgeBaseId=kb_id)
            return response.get("dataSourceSummaries", [])
        except ClientError as e:
            logger.error("data_source_list_failed", kb_id=kb_id, error=str(e))
            raise

    def get_data_source_id(self, kb_id: str, name: str) -> str | None:
        """Find a data source ID by its name within a KB."""
        try:
            for ds in self.list_data_sources(kb_id):
                if ds.get("name") == name:
                    return ds.get("dataSourceId")
            return None
        except Exception:
            return None

    def get_ingestion_job_status(self, kb_id: str, data_source_id: str, job_id: str) -> dict:
        """Get the status of an ingestion job."""
        try:
            response = self.client.get_ingestion_job(
                knowledgeBaseId=kb_id,
                dataSourceId=data_source_id,
                ingestionJobId=job_id,
            )
            return response.get("ingestionJob", {})
        except ClientError as e:
            logger.error("ingestion_status_failed", kb_id=kb_id, job_id=job_id, error=str(e))
            raise

    def delete_knowledge_base(self, kb_id: str) -> None:
        """Delete a Knowledge Base (and its associated data sources)."""
        try:
            self.client.delete_knowledge_base(knowledgeBaseId=kb_id)
            logger.info("kb_deleted", kb_id=kb_id)
        except ClientError as e:
            logger.error("kb_deletion_failed", kb_id=kb_id, error=str(e))
            raise
