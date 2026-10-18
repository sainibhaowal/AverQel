function resolveAverQelReturnUrl(lastAverQelUrl, appStartUrl) {
  const baseUrl = new URL(appStartUrl);
  const isWebOrigin =
    baseUrl.protocol === "https:" || baseUrl.protocol === "http:";
  if (!isWebOrigin)
    throw new Error("AverQel must use an HTTP or HTTPS application URL.");

  if (typeof lastAverQelUrl === "string" && lastAverQelUrl.trim()) {
    try {
      const candidate = new URL(lastAverQelUrl);
      if (
        (candidate.protocol === "https:" || candidate.protocol === "http:") &&
        candidate.origin === baseUrl.origin
      ) {
        return candidate.toString();
      }
    } catch {
      // Use the authenticated dashboard as the safe default below.
    }
  }

  return new URL("/dashboard", baseUrl).toString();
}

module.exports = { resolveAverQelReturnUrl };
