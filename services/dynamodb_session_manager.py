import boto3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from boto3.dynamodb.conditions import Key

class DynamoDBSessionMetadataManager:
    """
    DynamoDB-backed manager for session metadata (thread list).
    Stores session_id, user_id, title, and timestamps.
    """
    def __init__(self, table_name: str, region_name: str = "us-east-1"):
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
        self.table = self.dynamodb.Table(table_name)

    def create_or_update_session(self, session_id: str, user_id: str, title: str = "New Chat"):
        now = datetime.utcnow().isoformat()
        self.table.put_item(
            Item={
                "session_id": session_id,
                "user_id": user_id,
                "title": title,
                "updated_at": now,
                "created_at": now # Should ideally handle 'if not exists' but keeping it simple for now
            }
        )

    def list_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        # This assumes a GSI on user_id if session_id is the primary key
        # Or that user_id is the partition key and session_id is the sort key
        response = self.table.query(
            IndexName="user_id-index",
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
        return response.get("Items", [])

    def update_last_accessed(self, session_id: str):
        now = datetime.utcnow().isoformat()
        self.table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET updated_at = :t",
            ExpressionAttributeValues={":t": now}
        )
