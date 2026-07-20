"""Schemas for workspace file operations."""

from pydantic import BaseModel


class WorkspaceStatusResponse(BaseModel):
    status: str
    message: str


class FileWriteRequest(BaseModel):
    path: str
    content: str


class ResolveFolderRequest(BaseModel):
    name: str
    current_path: str
