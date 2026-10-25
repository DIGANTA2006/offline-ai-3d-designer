"""Compatibility package paths must point at the canonical implementations."""


def test_validation_compatibility_exports():
    from ai3d_designer.validation import GeometryValidator as LegacyGeometryValidator
    from ai3d_designer.core.validation import GeometryValidator as CoreGeometryValidator

    assert LegacyGeometryValidator is CoreGeometryValidator


def test_storage_compatibility_exports():
    from ai3d_designer.storage import SpecStorage as LegacySpecStorage
    from ai3d_designer.core.storage import SpecStorage as CoreSpecStorage

    assert LegacySpecStorage is CoreSpecStorage


def test_worker_compatibility_exports():
    from ai3d_designer.worker import WorkerPool as LegacyWorkerPool
    from ai3d_designer.core.worker import WorkerPool as CoreWorkerPool

    assert LegacyWorkerPool is CoreWorkerPool


def test_licensing_compatibility_exports():
    from ai3d_designer.licensing import LicenseManager as LegacyLicenseManager
    from ai3d_designer.core.licensing import LicenseManager as CoreLicenseManager

    assert LegacyLicenseManager is CoreLicenseManager
