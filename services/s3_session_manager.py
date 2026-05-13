import json
import boto3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime

class S3SessionManager:
    """
    S3-backed session manager for raw conversation history.
    Saves and restores the full message history for a session.
    """
    def __init__(self, bucket_name: str, region_name: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.s3 = boto3.client("s3", region_name=region_name)

    def _get_key(self, session_id: str) -> str:
        return f"sessions/{session_id}/history.json"

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=self._get_key(session_id))
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except self.s3.exceptions.NoSuchKey:
            return []
        except Exception as e:
            print(f"Error loading session from S3: {e}")
            return []

    def add_message(self, session_id: str, role: str, content: str):
        messages = self.get_messages(session_id)
        messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=self._get_key(session_id),
            Body=json.dumps(messages),
            ContentType="application/json"
        )
