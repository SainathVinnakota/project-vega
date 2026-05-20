"""
Platform Bootstrap Script — Standardized Multi-Agent Pipeline.
Automates KB, Memory, and AgentCore Deployment.
Follows the "minimal code per agent" vision.
"""

import os
import sys
import logging
import json
import boto3
from dotenv import load_dotenv, dotenv_values

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from adapters.aws.bedrock_kb_manager import BedrockKBManager  # noqa: E402
from control_plane.memory_manager import MemoryManager  # noqa: E402
from control_plane.deployment_manager import DeploymentManager  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("platform_bootstrap")


def bootstrap_agent(agent_id, bucket_name, role_arn, region="us-east-1"):
    """
    Standardized Pipeline:
    1. Create/Verify Knowledge Base
    2. Create/Verify AgentCore Memory
    3. Update Agent JSON Profile (Persistent Config)
    4. Deploy/Update AgentCore Runtime
    """
    kb_mgr = BedrockKBManager(
        region=region,
        role_arn=role_arn,
        embedding_model_arn="arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
    )
    kb_mgr._rds_resource_arn = os.environ.get("RDS_RESOURCE_ARN", "")
    kb_mgr._rds_credentials_secret_arn = os.environ.get("RDS_CREDENTIALS_SECRET_ARN", "")
    mem_mgr = MemoryManager(region)
    deploy_mgr = DeploymentManager(region)

    # Load existing profile to get defaults
    profile_path = os.path.join("profiles", f"{agent_id}.json")
    if not os.path.exists(profile_path):
        logger.error(f"Profile {profile_path} not found. Create it first.")
        return None

    with open(profile_path, "r") as f:
        profile = json.load(f)

    try:
        # --- 1. Knowledge Base ---
        kb_name = f"{agent_id}-kb"
        kb_ids = profile.get("retrieval_profile", {}).get("knowledge_base_ids", [])
        kb_id = kb_ids[0] if kb_ids else None

        # Check if KB already exists in AWS to avoid ConflictException
        if not kb_id:
            existing_id = kb_mgr.get_kb_id_by_name(kb_name)
            if existing_id:
                logger.info(f"Discovered existing Knowledge Base on AWS: {existing_id}")
                kb_id = existing_id

        if not kb_id:
            logger.info("Creating new Knowledge Base...")
            kb = kb_mgr.create_knowledge_base(
                name=kb_name,
                description=f"KB for {agent_id}",
                rds_resource_arn=kb_mgr._rds_resource_arn,
                rds_credentials_secret_arn=kb_mgr._rds_credentials_secret_arn,
            )
            kb_id = kb["knowledgeBaseId"]
            ds = kb_mgr.add_s3_data_source(
                kb_id=kb_id,
                s3_bucket=bucket_name,
                data_source_name=f"{agent_id}-s3",
            )
            ds_id = ds["dataSourceId"]
            kb_mgr.sync_data_source(kb_id, ds_id)
        else:
            logger.info(f"Using existing KB: {kb_id}")
            # Ensure Data Source exists
            ds_name = f"{agent_id}-s3"
            ds_id = kb_mgr.get_data_source_id(kb_id, ds_name)
            if not ds_id:
                logger.info("Adding missing Data Source to existing KB...")
                ds = kb_mgr.add_s3_data_source(
                    kb_id=kb_id,
                    s3_bucket=bucket_name,
                    data_source_name=ds_name,
                )
                ds_id = ds["dataSourceId"]
                kb_mgr.sync_data_source(kb_id, ds_id)

        # --- 2. AgentCore Memory ---
        # Note: AWS AgentCore Memory regex constraint only allows alphanumeric and underscores: [a-zA-Z][a-zA-Z0-9_]{0,47}
        mem_name = f"{agent_id}_memory"
        memory_id = profile.get("memory_profile", {}).get("memory_id")

        if not memory_id:
            existing_mem = mem_mgr.get_memory_id_by_name(mem_name)
            if existing_mem:
                logger.info(f"Discovered existing AgentCore Memory on AWS: {existing_mem}")
                memory_id = existing_mem

        if not memory_id:
            logger.info("Creating new AgentCore Memory...")
            memory_id = mem_mgr.create_memory(name=mem_name)
        else:
            logger.info(f"Using existing Memory: {memory_id}")

        # --- 3. Update Profile (Configuration-driven, no hardcoding) ---
        profile["retrieval_profile"]["knowledge_base_ids"] = [kb_id]
        profile["memory_profile"]["memory_id"] = memory_id
        profile["session_profile"]["bucket"] = bucket_name

        with open(profile_path, "w") as f:
            json.dump(profile, f, indent=2)
        logger.info(f"Updated profile: {profile_path}")

        # --- 4. Deployment ---
        # Image is built ONCE for the platform. We just run it with different AGENT_ID.
        container_uri = os.environ.get("ECR_IMAGE_URI")
        if not container_uri:
            logger.warning("ECR_IMAGE_URI not set. Deployment might fail or use placeholder.")
            container_uri = "placeholder-image-uri"

        # Dynamically propagate all string-valued local environment variables
        local_env = dotenv_values(".env")
        runtime_envs = {k: str(v) for k, v in local_env.items() if v is not None}
        runtime_envs["AGENT_ID"] = agent_id
        runtime_envs["MODEL_PROVIDER"] = profile.get("model_profile", {}).get("provider", "bedrock")
        runtime_envs["BEDROCK_MODEL_ID"] = profile.get("model_profile", {}).get(
            "model_id", "amazon.nova-pro-v1:0"
        )
        if profile.get("retrieval_profile", {}).get("knowledge_base_ids"):
            runtime_envs["BEDROCK_KB_ID"] = profile["retrieval_profile"]["knowledge_base_ids"][0]

        # Auto-resolve real AWS RDS cluster hostname if missing to prevent localhost connection refused errors
        if not runtime_envs.get("DB_HOST") and runtime_envs.get("RDS_CLUSTER_ARN"):
            try:
                cluster_id = runtime_envs["RDS_CLUSTER_ARN"].split(":")[-1]
                rds = boto3.client("rds", region_name=region)
                res = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
                clusters = res.get("DBClusters", [])
                if clusters:
                    # Prefer standard endpoint or reader endpoint string
                    resolved_host = clusters[0].get("Endpoint")
                    if resolved_host:
                        logger.info(
                            f"Auto-resolved true cloud RDS cluster endpoint: {resolved_host}"
                        )
                        runtime_envs["DB_HOST"] = resolved_host
                        runtime_envs["DB_PASSWORD"] = (
                            "dummy_secret_managed"  # Let IAM/Secret auth override or fallback cleanly
                        )
            except Exception as rds_err:
                logger.warning(f"Could not auto-resolve RDS host endpoint: {rds_err}")

        logger.info(
            f"Deploying/Updating AgentCore Runtime for {agent_id} with {len(runtime_envs)} runtime variables..."
        )
        runtime_arn = deploy_mgr.deploy_agent_runtime(
            name=agent_id, container_uri=container_uri, role_arn=role_arn, env_vars=runtime_envs
        )

        return {
            "agent_id": agent_id,
            "kb_id": kb_id,
            "memory_id": memory_id,
            "runtime_arn": runtime_arn,
        }

    except Exception as e:
        logger.error(f"Platform Bootstrap failed: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python scripts/platform_bootstrap.py <agent_id> <bucket_name> <role_arn>")
        sys.exit(1)

    target_agent = sys.argv[1]
    target_bucket = sys.argv[2]
    target_role = sys.argv[3]

    result = bootstrap_agent(target_agent, target_bucket, target_role)
    if result:
        print("\n=== Platform Bootstrap Successful ===")
        print(json.dumps(result, indent=2))
        print("=======================================")
    else:
        print("\n!!! Platform Bootstrap Failed !!!")
