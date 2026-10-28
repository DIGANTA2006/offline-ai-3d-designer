"""
Licensing module for offline license validation.
"""

import os
import json
import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


@dataclass
class LicenseInfo:
    """License information."""
    valid: bool
    license_type: str  # "trial", "pro", "enterprise"
    features: list[str]
    expires_at: Optional[str] = None
    issued_to: str = ""
    issued_at: str = ""
    signature: str = ""
    error: Optional[str] = None


class LicenseManager:
    """Manages offline license validation."""
    
    # Public key for verifying licenses (embedded)
    # In production, this would be a real RSA public key
    PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"""
    
    # License file location
    LICENSE_FILE_NAME = "license.key"
    
    def __init__(self, license_dir: Optional[str] = None):
        if license_dir is None:
            from appdirs import user_data_dir
            license_dir = user_data_dir("ai3d-designer", "OfflineAI3DDesigner")
        self.license_dir = Path(license_dir)
        self.license_dir.mkdir(parents=True, exist_ok=True)
        self.license_path = self.license_dir / self.LICENSE_FILE_NAME
        self._cached_license: Optional[LicenseInfo] = None
    
    def validate_license(self, force_refresh: bool = False) -> LicenseInfo:
        """Validate the current license."""
        if self._cached_license and not force_refresh:
            return self._cached_license
        
        # Check for license file
        if not self.license_path.exists():
            # No license - return trial
            self._cached_license = LicenseInfo(
                valid=True,
                license_type="trial",
                features=["basic_geometry", "step_export", "stl_export"],
                issued_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            )
            return self._cached_license
        
        try:
            with open(self.license_path, 'r') as f:
                license_data = json.load(f)
            
            # Verify signature
            if not self._verify_signature(license_data):
                self._cached_license = LicenseInfo(
                    valid=False,
                    license_type="invalid",
                    features=[],
                    error="Invalid license signature"
                )
                return self._cached_license
            
            # Check expiration
            expires_at = license_data.get("expires_at")
            if expires_at:
                exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now(timezone.utc).replace(tzinfo=None) > exp_date:
                    self._cached_license = LicenseInfo(
                        valid=False,
                        license_type="expired",
                        features=license_data.get("features", []),
                        expires_at=expires_at,
                        issued_to=license_data.get("issued_to", ""),
                        issued_at=license_data.get("issued_at", ""),
                        error="License has expired"
                    )
                    return self._cached_license
            
            # Valid license
            self._cached_license = LicenseInfo(
                valid=True,
                license_type=license_data.get("license_type", "pro"),
                features=license_data.get("features", []),
                expires_at=expires_at,
                issued_to=license_data.get("issued_to", ""),
                issued_at=license_data.get("issued_at", ""),
                signature=license_data.get("signature", ""),
            )
            return self._cached_license
            
        except Exception as e:
            self._cached_license = LicenseInfo(
                valid=False,
                license_type="error",
                features=[],
                error=f"License validation error: {str(e)}"
            )
            return self._cached_license
    
    def _verify_signature(self, license_data: Dict[str, Any]) -> bool:
        """Verify license signature."""
        # For trial/offline mode, we accept a simple HMAC-based validation
        # In production, use proper RSA verification
        signature = license_data.get("signature", "")
        if not signature:
            return False
        
        # Create data to verify (exclude signature)
        verify_data = {k: v for k, v in license_data.items() if k != "signature"}
        data_str = json.dumps(verify_data, sort_keys=True, separators=(',', ':'))
        
        # Simple HMAC check with a derived key (for offline validation)
        # This is a placeholder - real implementation would use RSA
        expected_sig = self._compute_hmac(data_str)
        return hmac.compare_digest(signature, expected_sig)
    
    def _compute_hmac(self, data: str) -> str:
        """Compute HMAC for license data."""
        # Use a device-specific key derived from hardware info
        device_id = self._get_device_id()
        key = hashlib.pbkdf2_hmac('sha256', device_id.encode(), b'ai3d-license-salt', 100000)
        sig = hmac.new(key, data.encode(), hashlib.sha256).hexdigest()
        return sig
    
    def _get_device_id(self) -> str:
        """Get a stable device identifier."""
        # Use machine ID or generate one
        try:
            import uuid
            # Try to get machine ID
            if os.name == 'nt':
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                    r"SOFTWARE\Microsoft\Cryptography")
                machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                winreg.CloseKey(key)
                return machine_guid
        except Exception:
            pass
        
        # Fallback to generated UUID stored in license dir
        id_file = self.license_dir / ".device_id"
        if id_file.exists():
            return id_file.read_text().strip()
        
        new_id = str(uuid.uuid4())
        id_file.write_text(new_id)
        return new_id
    
    def install_license(self, license_key: str) -> LicenseInfo:
        """Install a license from key string."""
        try:
            # Decode license key (base64 encoded JSON)
            decoded = base64.b64decode(license_key).decode('utf-8')
            license_data = json.loads(decoded)
            
            # Validate structure
            required_fields = ["license_type", "features", "issued_to", "issued_at", "signature"]
            for field in required_fields:
                if field not in license_data:
                    return LicenseInfo(
                        valid=False,
                        license_type="invalid",
                        features=[],
                        error=f"Missing required field: {field}"
                    )
            
            # Save license file
            with open(self.license_path, 'w') as f:
                json.dump(license_data, f, indent=2)
            
            # Clear cache and validate
            self._cached_license = None
            return self.validate_license(force_refresh=True)
            
        except Exception as e:
            return LicenseInfo(
                valid=False,
                license_type="invalid",
                features=[],
                error=f"Failed to install license: {str(e)}"
            )
    
    def get_license_status(self) -> Dict[str, Any]:
        """Get human-readable license status."""
        info = self.validate_license()
        
        status = {
            "valid": info.valid,
            "type": info.license_type,
            "features": info.features,
            "issued_to": info.issued_to,
        }
        
        if info.expires_at:
            exp_date = datetime.fromisoformat(info.expires_at.replace('Z', '+00:00'))
            days_left = (exp_date - datetime.now(timezone.utc).replace(tzinfo=None)).days
            status["expires_at"] = info.expires_at
            status["days_remaining"] = max(0, days_left)
            if days_left <= 30:
                status["warning"] = f"License expires in {days_left} days"
        
        if info.error:
            status["error"] = info.error
        
        return status
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled by license."""
        info = self.validate_license()
        if not info.valid:
            return False
        
        # Trial features
        trial_features = ["basic_geometry", "step_export", "stl_export"]
        if info.license_type == "trial":
            return feature in trial_features
        
        # Pro/Enterprise - check explicit features or allow all
        if info.license_type in ("pro", "enterprise"):
            return feature in info.features or "all" in info.features
        
        return False


# Global license manager
_license_manager: Optional[LicenseManager] = None


def get_license_manager(license_dir: Optional[str] = None) -> LicenseManager:
    """Get the global license manager."""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager(license_dir)
    return _license_manager
