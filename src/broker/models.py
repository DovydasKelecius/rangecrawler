from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import subprocess

class ModelInstance(BaseModel):
    model_id: str
    port: int
    process: Optional[object] = Field(None, exclude=True) # subprocess.Popen object
    start_time: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    active_requests: int = 0
    status: str = "loading" # loading, running, stopping, crashed

    class Config:
        arbitrary_types_allowed = True

class ModelStatus(BaseModel):
    model_id: str
    instances: List[ModelInstance]
    total_active_requests: int
