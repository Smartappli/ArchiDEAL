# Security platform component

Prerequisites:

- External Secrets Operator with a `ClusterSecretStore` named `dealiot-secret-store`.
- Kyverno 1.18 or newer with `ImageValidatingPolicy` CRDs installed.
- GitHub Actions keyless signatures created by the protected main-branch image workflow.

Patch remote secret keys for the selected provider, then add this component to the site-specific
production overlay. Do not add literal secret values to this directory.
