# Release security controls

The release and deployment workflows are manual and protected by `main`.

## Desktop signing

Run `Release - Manual SemVer and Desktop` with `sign_desktop: true` only after
these repository secrets are configured:

- `WINDOWS_CERTIFICATE_BASE64`: base64-encoded Authenticode `.pfx` certificate.
- `WINDOWS_CERTIFICATE_PASSWORD`: password for that certificate.
- `APPLE_CERTIFICATE`: base64-encoded Apple Developer ID `.p12` certificate.
- `APPLE_CERTIFICATE_PASSWORD`: password for that certificate.
- `APPLE_SIGNING_IDENTITY`: exact Developer ID Application identity.
- `APPLE_ID`: Apple ID used for notarization.
- `APPLE_PASSWORD`: app-specific Apple notarization password.
- `APPLE_TEAM_ID`: Apple Developer Team ID.

When enabled, the workflow fails if any secret is missing, signs the Windows
installer, verifies it with `signtool`, signs the macOS application, and runs
macOS notarization validation with `stapler`. Secrets are never written to the
repository or included in release assets.

When disabled, packages are still built, checksummed, and scanned, but are not
claimed to be signed.

## Images and artifacts

- Desktop releases include `SHA256SUMS.txt` and `release-manifest.json`.
- Deployment verifies the checksums before uploading anything to the VPS.
- Docker images are scanned for high and critical vulnerabilities.
- Published images receive keyless Cosign signatures through GitHub OIDC and
  are verified in the same workflow before deployment.
- SBOM files are retained as GitHub Actions artifacts.

## VPS safety

Downloads are assembled in an immutable version directory and `latest` is
switched atomically only after health checks and public URL checks succeed.
The previous application image is kept for immediate rollback. Five canonical
desktop release directories are retained; unrelated VPS files, volumes, models,
and containers are not removed.
