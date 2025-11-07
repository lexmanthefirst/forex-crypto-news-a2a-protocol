"""
A2A Protocol Models
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal, Optional, List, Dict, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class MessagePart(BaseModel):
    """Message part - can be text, data, or file.
    """
    kind: Literal["text", "data", "file"]
    text: Optional[str] = None
    data: Optional[Union[Dict[str, Any], List[Any]]] = None
    fileUrl: Optional[str] = None


class A2AMessage(BaseModel):
    """A2A message format."""
    kind: Literal["message"] = "message"
    role: Literal["user", "agent", "system"]
    parts: List[MessagePart]
    messageId: str = Field(default_factory=lambda: str(uuid4()))
    taskId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PushNotificationConfig(BaseModel):
    """Configuration for push notifications."""
    url: str
    token: Optional[str] = None
    authentication: Optional[Dict[str, Any]] = None


class MessageConfiguration(BaseModel):
    """Configuration for message sending."""
    blocking: bool = True
    acceptedOutputModes: List[str] = ["text/plain", "image/png", "image/svg+xml"]
    pushNotificationConfig: Optional[PushNotificationConfig] = None


class MessageParams(BaseModel):
    """Parameters for message/send method (Telex-compatible)."""
    messages: List[A2AMessage]  # Note: PLURAL, it's a list
    contextId: Optional[str] = None
    taskId: Optional[str] = None
    config: Optional[Dict[str, Any]] = Field(default=None, alias="configuration")


class ExecuteParams(BaseModel):
    """Parameters for execute method."""
    contextId: Optional[str] = None
    taskId: Optional[str] = None
    messages: List[A2AMessage]
    configuration: Optional[Dict[str, Any]] = None


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request."""
    jsonrpc: Literal["2.0"]
    id: str
    method: Literal["message/send", "execute"]
    params: MessageParams | ExecuteParams


class TaskStatus(BaseModel):
    """Task status information."""
    state: Literal["working", "completed", "input-required", "failed"]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: Optional[A2AMessage] = None


class Artifact(BaseModel):
    """Artifact attached to a task."""
    artifactId: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    parts: List[MessagePart]


class TaskResult(BaseModel):
    """Result of a task execution."""
    taskId: str
    contextId: str
    status: TaskStatus
    artifacts: List[Artifact] = []
    history: List[A2AMessage] = []
    kind: Literal["task"] = "task"


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response."""
    jsonrpc: Literal["2.0"] = "2.0"
    id: str
    result: Optional[TaskResult] = None
    error: Optional[Dict[str, Any]] = None

    def model_dump(self, **kwargs):
        """Ensure proper JSON-RPC response format.
        
        JSON-RPC 2.0 spec: response must have either 'result' OR 'error', never both.
        - Include 'result' field when successful
        - Include 'error' field when failed
        - Exclude the other field
        """
        data = super().model_dump(**kwargs)
        
        # Remove error field if it's None (proper JSON-RPC: either result or error, never both)
        if self.error is None and 'error' in data:
            del data['error']
        
        # Remove result field if error is present
        if self.error is not None and 'result' in data:
            del data['result']
        
        return data