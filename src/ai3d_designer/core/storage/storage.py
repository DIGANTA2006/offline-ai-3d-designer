"""
Storage module for saving/loading PartSpec and project files.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..spec.models import PartSpec


@dataclass
class ProjectMetadata:
    """Metadata for a saved project."""
    name: str
    description: str
    created_at: str
    updated_at: str
    version: str = "0.1.0"
    tags: List[str] = None
    thumbnail_path: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SpecStorage:
    """Handles persistence of PartSpec objects."""
    
    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            # Default to user data directory
            from appdirs import user_data_dir
            base_dir = user_data_dir("ai3d-designer", "OfflineAI3DDesigner")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir = self.base_dir / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir = self.base_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
    
    def save_spec(self, spec: PartSpec, name: Optional[str] = None) -> str:
        """
        Save a PartSpec to JSON file.
        
        Returns:
            Path to saved file
        """
        file_name = name or f"{spec.name}_{spec.id}.json"
        file_path = self.specs_dir / file_name
        
        # Ensure .json extension
        if not file_path.suffix:
            file_path = file_path.with_suffix(".json")
        
        data = spec.model_dump(mode="json")
        data["_saved_at"] = datetime.utcnow().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        
        return str(file_path)
    
    def load_spec(self, file_path: str) -> PartSpec:
        """Load a PartSpec from JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Spec file not found: {file_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Remove internal fields
        data.pop("_saved_at", None)
        
        return PartSpec(**data)
    
    def list_specs(self) -> List[Dict[str, Any]]:
        """List all saved specs with metadata."""
        specs = []
        for file_path in self.specs_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                specs.append({
                    "file": str(file_path),
                    "name": data.get("name", file_path.stem),
                    "id": data.get("id", ""),
                    "description": data.get("description", ""),
                    "feature_count": len(data.get("features", [])),
                    "saved_at": data.get("_saved_at", ""),
                })
            except Exception:
                continue
        return sorted(specs, key=lambda x: x.get("saved_at", ""), reverse=True)
    
    def delete_spec(self, file_path: str) -> bool:
        """Delete a saved spec."""
        path = Path(file_path)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def save_project(self, name: str, spec: PartSpec, 
                     description: str = "", tags: List[str] = None) -> str:
        """Save a complete project with metadata."""
        project_dir = self.projects_dir / name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Save spec
        spec_path = project_dir / "spec.json"
        self.save_spec(spec, str(spec_path))
        
        # Save metadata
        metadata = ProjectMetadata(
            name=name,
            description=description,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            tags=tags or [],
        )
        metadata_path = project_dir / "metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata.__dict__, f, indent=2)
        
        return str(project_dir)
    
    def load_project(self, project_path: str) -> tuple[PartSpec, ProjectMetadata]:
        """Load a project."""
        path = Path(project_path)
        spec = self.load_spec(str(path / "spec.json"))
        
        metadata_path = path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            metadata = ProjectMetadata(**meta_data)
        else:
            metadata = ProjectMetadata(
                name=path.name,
                description="",
                created_at=datetime.utcnow().isoformat(),
                updated_at=datetime.utcnow().isoformat(),
            )
        
        return spec, metadata
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        projects = []
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir():
                metadata_path = project_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    projects.append({
                        "path": str(project_dir),
                        "name": meta.get("name", project_dir.name),
                        "description": meta.get("description", ""),
                        "tags": meta.get("tags", []),
                        "created_at": meta.get("created_at", ""),
                        "updated_at": meta.get("updated_at", ""),
                    })
        return sorted(projects, key=lambda x: x.get("updated_at", ""), reverse=True)


# Global storage instance
_default_storage: Optional[SpecStorage] = None


def get_storage(base_dir: Optional[str] = None) -> SpecStorage:
    """Get the default storage instance."""
    global _default_storage
    if _default_storage is None:
        _default_storage = SpecStorage(base_dir)
    return _default_storage
