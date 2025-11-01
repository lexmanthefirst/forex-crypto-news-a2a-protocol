from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# Define models for A2A messaging system
class MessagePart(BaseModel):
    kind: Literal["text", "data", "file"]
    text: str | None = None
    data: dict[str, Any] | None = None
    file_url: str | None = None

class A2AMessage(BaseModel):
    kind: Literal["message"] = "message"
    role: Literal["user", "agent", "system"]
    parts: list[MessagePart]
    messageId: str = Field(default_factory=lambda: str(uuid4()))
    taskId: str | None = None
    metadata: dict[str, Any] | None = None

# Configure message sending options
class PushNotificationConfig(BaseModel):
    url: str
    token: str | None = None
    authentication: dict[str, Any] | None = None

class MessageConfiguration(BaseModel):
    blocking: bool = True
    acceptedOutputModes: list[str] = Field(default_factory=lambda: ["text/plain", "application/json"])
    pushNotification: PushNotificationConfig | None = None

# Params objects for JSON-RPC
class MessageParams(BaseModel):
    message: A2AMessage
    configuration: MessageConfiguration = Field(default_factory=MessageConfiguration)

class ExecuteParams(BaseModel):
    contextId: str | None = None
    taskId: str | None = None
    messages: list[A2AMessage]

# JSON-RPC request models
class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str
    method: Literal["message/send", "execute"]
    params: MessageParams | ExecuteParams

class TaskStatus(BaseModel):
    state: Literal["working", "completed", "input-required", "failed"]
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    message: A2AMessage | None = None

class Artifact(BaseModel):
    artifactId: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    parts: list[MessagePart]

class TaskResult(BaseModel):
    id: str
    contextId: str
    status: TaskStatus
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[A2AMessage] = Field(default_factory=list)
    kind: Literal["task"] = "task"

class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"]
    id: str
    result: TaskResult | None = None
    error: dict[str, Any] | None = None