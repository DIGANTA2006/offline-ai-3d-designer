/**
 * Client for communicating with the Python CAD microservice.
 * All secrets/API keys stay on the server; this client only calls our own API routes.
 */

const CAD_SERVICE_URL = process.env.CAD_SERVICE_URL ?? "http://127.0.0.1:8000";

export interface OcrRequest {
  fileBase64: string;
  fileName: string;
  mimeType: string;
}

export interface ExtractedSpec {
  dimensions: Record<string, number>;
  tolerances: Record<string, { nominal: number; upper: number; lower: number }>;
  fits: Array<{ feature: string; type: "clearance" | "interference" | "transition"; shaft: number; hole: number }>;
  material?: string;
  surfaceFinish?: string;
  threads?: Array<{ designation: string; pitch: number; class: string }>;
  views: Array<{ name: string; bounds: [number, number, number, number] }>;
  annotations: string[];
  confidence: number;
  rawText: string;
}

export interface OcrResponse {
  success: boolean;
  spec?: ExtractedSpec;
  error?: string;
  jobId: string;
}

export interface GenerationRequest {
  spec: ExtractedSpec;
  jobId: string;
  userId: string;
}

export interface GenerationResponse {
  success: boolean;
  stepUrl?: string;
  stlUrl?: string;
  glbUrl?: string;
  fitReport?: string;
  isApproximation?: boolean;
  error?: string;
  version: number;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "down";
  version: string;
  ocrAvailable: boolean;
  cadAvailable: boolean;
  imageTo3dAvailable: boolean;
}

// New text-to-cad types
export interface TextToCadRequest {
  text: string;
  userId: string;
  unitSystem: string;
  exportFormats: string[];
}

export interface TextToCadResponse {
  success: boolean;
  partSpec?: Record<string, unknown>;
  stepBase64?: string;
  stlBase64?: string;
  validationErrors: string[];
  error?: string;
}

/**
 * Call the CAD service OCR endpoint.
 */
export async function callOcrEndpoint(request: OcrRequest): Promise<OcrResponse> {
  const response = await fetch(`${CAD_SERVICE_URL}/api/v1/ocr/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "OCR service unavailable" }));
    throw new Error(error.detail ?? `OCR request failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Call the CAD service generation endpoint.
 */
export async function callGenerationEndpoint(request: GenerationRequest): Promise<GenerationResponse> {
  const response = await fetch(`${CAD_SERVICE_URL}/api/v1/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Generation service unavailable" }));
    throw new Error(error.detail ?? `Generation request failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Convert natural language to CAD model.
 */
export async function callTextToCadEndpoint(request: TextToCadRequest): Promise<TextToCadResponse> {
  const response = await fetch(`${CAD_SERVICE_URL}/api/v1/text-to-cad`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Text-to-CAD service unavailable" }));
    throw new Error(error.detail ?? `Text-to-CAD request failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Check CAD service health.
 */
export async function checkCadServiceHealth(): Promise<HealthResponse> {
  try {
    const response = await fetch(`${CAD_SERVICE_URL}/health`, { method: "GET" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  } catch {
    return {
      status: "down",
      version: "unknown",
      ocrAvailable: false,
      cadAvailable: false,
      imageTo3dAvailable: false,
    };
  }
}
