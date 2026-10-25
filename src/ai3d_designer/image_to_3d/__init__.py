"""Image-to-3D utilities with optional model dependencies.

Core mesh helpers remain importable when Torch/OpenCV are not installed.
"""
IMAGE_TO_3D_IMPORT_ERROR = None
try:
    from .converter import ImageTo3DConverter, create_lithophane
except ImportError as exc:
    ImageTo3DConverter = None
    create_lithophane = None
    IMAGE_TO_3D_IMPORT_ERROR = str(exc)

__all__ = ["ImageTo3DConverter", "create_lithophane", "IMAGE_TO_3D_IMPORT_ERROR"]
