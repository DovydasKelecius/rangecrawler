import asyncio
import subprocess
import time
import socket
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import torch

from .models import ModelInstance
from .config import AppConfig

class ModelManager:
    def __init__(self, config: AppConfig):
        self.config = config.broker
        self.allowed_models = {m.id: m for m in config.models}
        self.instances: Dict[str, List[ModelInstance]] = {}
        self.lock = asyncio.Lock()
        self._used_ports = set()
        self.logger = logging.getLogger("ModelManager")
        
        # Simple request queue: model_id -> list of futures
        self.queues: Dict[str, List[asyncio.Future]] = {}

    def _get_free_port(self) -> int:
        port = self.config.base_vllm_port
        while port in self._used_ports or self._is_port_in_use(port):
            port += 1
        self._used_ports.add(port)
        return port

    def _is_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    async def get_instance(self, model_id: str) -> ModelInstance:
        if model_id not in self.allowed_models:
            raise ValueError(f"Model {model_id} is not in the allowed list")

        async with self.lock:
            if model_id not in self.instances:
                self.instances[model_id] = []

            # 1. Try to find an existing running instance
            running_instances = [inst for inst in self.instances[model_id] if inst.status == "running"]
            if running_instances:
                instance = min(running_instances, key=lambda x: x.active_requests)
                instance.active_requests += 1
                instance.last_active = datetime.now()
                return instance

            # 2. Check if we are already loading this model
            loading_instances = [inst for inst in self.instances[model_id] if inst.status == "loading"]
            if loading_instances:
                # Wait for the first loading instance to become ready
                # (Simple queuing logic)
                fut = asyncio.get_event_loop().create_future()
                if model_id not in self.queues:
                    self.queues[model_id] = []
                self.queues[model_id].append(fut)
                
                self.logger.info(f"Queuing request for {model_id}, waiting for instance to load...")
                return await fut

            # 3. If no instance exists/loading, start one
            return await self._start_instance(model_id)

    async def _start_instance(self, model_id: str) -> ModelInstance:
        port = self._get_free_port()
        self.logger.info(f"Starting vLLM for model {model_id} on port {port}")
        
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", model_id,
            "--port", str(port),
            "--gpu-memory-utilization", str(self.config.gpu_memory_utilization),
            "--disable-log-requests"
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            instance = ModelInstance(
                model_id=model_id,
                port=port,
                process=process,
                status="loading",
                active_requests=1
            )
            self.instances[model_id].append(instance)
            
            # Non-blocking wait in a separate task so we don't hold the manager lock
            # But wait, we need to return the instance or wait here. 
            # Re-architecting slightly to handle async startup better.
            
            if await self._wait_for_ready(instance):
                instance.status = "running"
                self.logger.info(f"Model {model_id} is ready on port {port}")
                
                # Notify queued requests
                if model_id in self.queues:
                    for fut in self.queues[model_id]:
                        if not fut.done():
                            instance.active_requests += 1
                            fut.set_result(instance)
                    self.queues[model_id] = []
                    
                return instance
            else:
                instance.status = "crashed"
                self.logger.error(f"Failed to start vLLM for model {model_id}")
                await self.unload_instance(instance)
                # Fail queued requests
                if model_id in self.queues:
                    for fut in self.queues[model_id]:
                        if not fut.done():
                            fut.set_exception(RuntimeError(f"vLLM failed to start for {model_id}"))
                    self.queues[model_id] = []
                raise RuntimeError(f"vLLM failed to start for {model_id}")
                
        except Exception as e:
            self.logger.error(f"Error launching vLLM: {e}")
            if port in self._used_ports:
                self._used_ports.remove(port)
            raise

    async def _wait_for_ready(self, instance: ModelInstance, timeout: int = 300) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if process is still running
            exit_code = instance.process.poll()
            if exit_code is not None:
                # Capture some error output if possible
                if instance.process.stdout:
                    error_log = instance.process.stdout.read(500)
                    self.logger.error(f"vLLM process for {instance.model_id} exited with code {exit_code}. Log snippet: {error_log}")
                return False
            
            if self._is_port_in_use(instance.port):
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(f"http://localhost:{instance.port}/health", timeout=1.0)
                        if resp.status_code == 200:
                            return True
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass
            await asyncio.sleep(2)
        
        self.logger.error(f"Timed out waiting for {instance.model_id} to start on port {instance.port}")
        return False

    async def release_instance(self, instance: ModelInstance):
        async with self.lock:
            instance.active_requests = max(0, instance.active_requests - 1)
            instance.last_active = datetime.now()

    async def unload_instance(self, instance: ModelInstance):
        self.logger.info(f"Unloading model {instance.model_id} on port {instance.port}")
        if instance.process:
            instance.process.terminate()
            try:
                instance.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                instance.process.kill()
        
        if instance.port in self._used_ports:
            self._used_ports.remove(instance.port)
            
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            self.logger.info("GPU cache cleared")

    async def cleanup_idle(self):
        while True:
            await asyncio.sleep(self.config.check_interval)
            async with self.lock:
                now = datetime.now()
                for model_id, instances in list(self.instances.items()):
                    for inst in list(instances):
                        idle_time = (now - inst.last_active).total_seconds()
                        if inst.active_requests == 0 and idle_time > self.config.idle_timeout:
                            await self.unload_instance(inst)
                            instances.remove(inst)
                    
                    if not instances:
                        del self.instances[model_id]
