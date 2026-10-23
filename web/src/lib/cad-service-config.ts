export type CadServiceConfig = {
  baseUrl: URL;
  token?: string;
};

export class CadServiceConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CadServiceConfigurationError";
  }
}

/**
 * Resolve the Python backend without allowing Vercel Preview deployments to
 * silently call the Production CAD service. Local development may still use
 * the default localhost backend when no URL is configured.
 */
export function getCadServiceConfig(): CadServiceConfig {
  const isPreview = process.env.VERCEL_ENV === "preview";
  const urlVariable = isPreview ? "CAD_SERVICE_URL_PREVIEW" : "CAD_SERVICE_URL";
  const tokenVariable = isPreview ? "CAD_SERVICE_TOKEN_PREVIEW" : "CAD_SERVICE_TOKEN";
  let rawUrl = process.env[urlVariable]?.trim();

  if (!rawUrl && isPreview) {
    throw new CadServiceConfigurationError(
      "CAD_SERVICE_URL_PREVIEW is required for Vercel Preview. Deploy a separate Python CAD backend from the feature branch and set this variable to that backend's HTTPS URL. Preview must not fall back to the Production CAD service.",
    );
  }
  if (!rawUrl && process.env.NODE_ENV !== "production") {
    rawUrl = "http://127.0.0.1:8000";
  }
  if (!rawUrl) {
    throw new CadServiceConfigurationError(`${urlVariable} is not configured in this deployment.`);
  }

  let baseUrl: URL;
  try {
    baseUrl = new URL(rawUrl);
  } catch {
    throw new CadServiceConfigurationError(`${urlVariable} is not a valid URL.`);
  }

  const isLoopback = ["localhost", "127.0.0.1", "::1"].includes(baseUrl.hostname);
  if (
    baseUrl.protocol !== "https:" &&
    !(process.env.NODE_ENV !== "production" && baseUrl.protocol === "http:" && isLoopback)
  ) {
    throw new CadServiceConfigurationError("The deployed CAD service must use HTTPS.");
  }

  const token = process.env[tokenVariable]?.trim() || undefined;
  if (!token && (isPreview || process.env.NODE_ENV === "production")) {
    throw new CadServiceConfigurationError(`${tokenVariable} is not configured in this deployment.`);
  }

  return { baseUrl, token };
}
