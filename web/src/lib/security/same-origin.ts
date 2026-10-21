export function isSameOriginRequest(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) {
    // Allow requests without origin in development (e.g., same-origin fetch without explicit origin)
    const isDev = process.env.NODE_ENV !== "production";
    if (isDev) return true;
    return false;
  }

  try {
    const requestOrigin = new URL(origin).origin;
    const requestUrlOrigin = new URL(request.url).origin;
    
    // Allow same origin
    if (requestOrigin === requestUrlOrigin) return true;
    
    // In development, allow localhost cross-port (e.g., 3000 -> 3000)
    const isDev = process.env.NODE_ENV !== "production";
    if (isDev) {
      const originHost = new URL(origin).host;
      const urlHost = new URL(request.url).host;
      // Allow localhost with different ports
      if (originHost.startsWith("localhost:") && urlHost.startsWith("localhost:")) {
        return true;
      }
      // Allow 127.0.0.1 with different ports
      if (originHost.startsWith("127.0.0.1:") && urlHost.startsWith("127.0.0.1:")) {
        return true;
      }
    }
    
    return false;
  } catch {
    return false;
  }
}
