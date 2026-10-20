"""
Worker module for background processing of CAD operations.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Callable, Dict, List
from concurrent.futures import ThreadPoolExecutor
import traceback


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Background job representation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    func: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    result: Any = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkerPool:
    """Thread pool for running CAD operations in background."""
    
    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._jobs: Dict[str, Job] = {}
        self._callbacks: Dict[str, List[Callable[[Job], None]]] = {}
    
    def start(self):
        """Start the worker pool."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
    
    def stop(self, wait: bool = True):
        """Stop the worker pool."""
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None
    
    def submit(self, job: Job) -> str:
        """Submit a job for execution."""
        if self._executor is None:
            self.start()
        
        self._jobs[job.id] = job
        
        # Submit to thread pool
        future = self._executor.submit(self._run_job, job)
        job.metadata["_future"] = future
        
        return job.id
    
    def _run_job(self, job: Job) -> Any:
        """Run a job and update its status."""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow().isoformat()
        job.progress = 0.0
        self._notify_callbacks(job)
        
        try:
            if job.func is None:
                raise ValueError("Job has no function to execute")
            
            # Execute the function
            result = job.func(*job.args, **job.kwargs)
            
            job.result = result
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.completed_at = datetime.utcnow().isoformat()
            
        except Exception as e:
            job.error = f"{type(e).__name__}: {str(e)}"
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow().isoformat()
            # Print traceback for debugging
            traceback.print_exc()
        
        finally:
            # Clean up future reference
            job.metadata.pop("_future", None)
            self._notify_callbacks(job)
        
        return job.result
    
    def _notify_callbacks(self, job: Job):
        """Notify registered callbacks of job update."""
        for callback in self._callbacks.get(job.id, []):
            try:
                callback(job)
            except Exception:
                pass  # Ignore callback errors
    
    def add_callback(self, job_id: str, callback: Callable[[Job], None]):
        """Add a callback for job updates."""
        if job_id not in self._callbacks:
            self._callbacks[job_id] = []
        self._callbacks[job_id].append(callback)
    
    def remove_callback(self, job_id: str, callback: Callable[[Job], None]):
        """Remove a callback."""
        if job_id in self._callbacks:
            try:
                self._callbacks[job_id].remove(callback)
            except ValueError:
                pass
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self._jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending/running job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        
        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            # Try to cancel the future
            future = job.metadata.get("_future")
            if future:
                future.cancel()
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.utcnow().isoformat()
            job.error = "Cancelled by user"
            self._notify_callbacks(job)
            return True
        
        return False
    
    def list_jobs(self, status: Optional[JobStatus] = None) -> List[Job]:
        """List all jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
    
    def clear_completed(self, max_age_hours: int = 24):
        """Clear old completed jobs."""
        now = datetime.utcnow()
        to_remove = []
        for job_id, job in self._jobs.items():
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                if job.completed_at:
                    completed = datetime.fromisoformat(job.completed_at)
                    age_hours = (now - completed).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(job_id)
        
        for job_id in to_remove:
            del self._jobs[job_id]
            self._callbacks.pop(job_id, None)


# Global worker pool
_worker_pool: Optional[WorkerPool] = None


def get_worker_pool(max_workers: int = 2) -> WorkerPool:
    """Get the global worker pool."""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool(max_workers)
    return _worker_pool


# Convenience functions for common CAD operations
def create_geometry_job(spec, name: str = "Create Geometry") -> Job:
    """Create a job for geometry generation."""
    from ..geometry.engine import create_part_from_spec
    return Job(
        name=name,
        func=create_part_from_spec,
        args=(spec,),
    )


def create_export_job(part, file_path: str, format: str = "step", name: str = "Export") -> Job:
    """Create a job for export."""
    from ..export.exporter import export_step, export_stl
    
    if format.lower() == "step":
        func = export_step
    elif format.lower() == "stl":
        func = export_stl
    else:
        raise ValueError(f"Unsupported format: {format}")
    
    return Job(
        name=name,
        func=func,
        args=(part, file_path),
    )


def create_validate_job(part, name: str = "Validate Geometry") -> Job:
    """Create a job for geometry validation."""
    from ..validation.validator import validate_geometry
    return Job(
        name=name,
        func=validate_geometry,
        args=(part,),
    )
