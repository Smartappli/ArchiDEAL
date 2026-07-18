# Production supply-chain contract

Production promotion accepts one signed release record containing exactly the ten images used by
the Kubernetes values file. Eight are built by ArchiDEAL and two are upstream runtime images. A
digest alone is not a release authorization.

## Trust root

`deploy/kubernetes/supply-chain-policy.yaml` is the reviewed allowlist. It fixes the GitHub
repository, release workflow path, main-branch ref, Sigstore issuer and certificate identity, plus
the only accepted repository for every image value key. The signed manifest contains the SHA-256
of this policy. Run deployment tooling from a clean Git worktree whose `HEAD` is the manifest
revision; a dirty checkout, different commit or different policy fails verification, including
during rollback.

The release workflow signs with GitHub Actions workload identity. It uses no long-lived signing
key. Production verification permits only:

- issuer `https://token.actions.githubusercontent.com`;
- identity
  `https://github.com/Smartappli/ArchiDEAL/.github/workflows/release-images.yml@refs/heads/main`.

Cosign verification also requires the certificate's GitHub repository, ref, workflow SHA and
trigger claims to equal the signed manifest; matching only the issuer is insufficient.

Branch protection must require Component CI, Architecture Smoke, Production manifests and Security
on the exact commit before it reaches `main`. The release workflow is not a substitute for those
required checks.

## Upstream inputs

Configure these non-secret GitHub repository variables before releasing:

| Variable | Required form | Enforced release contract |
| --- | --- | --- |
| `ARCHIDEAL_APISIX_IMAGE` | `apache/apisix@sha256:<64 lowercase hex>` | APISIX 3.14.1 or newer |
| `ARCHIDEAL_APISIX_SOURCE_RELEASE` | `https://github.com/apache/apisix/releases/tag/<tag>` | The registry tag is exactly `<tag>-debian` |
| `ARCHIDEAL_OAUTH2_PROXY_IMAGE` | `quay.io/oauth2-proxy/oauth2-proxy@sha256:<64 lowercase hex>` | oauth2-proxy 7.15.3 or newer |
| `ARCHIDEAL_OAUTH2_PROXY_SOURCE_RELEASE` | `https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/<tag>` | The registry tag is exactly `<tag>` |

The two upstream publishers are not assumed to provide a compatible Cosign identity. The release
workflow therefore applies an explicit compensating contract to the exact upstream digests. Only
stable semantic source tags at or above the policy floor are accepted. The approved image tag is
derived rather than supplied independently: APISIX uses the source tag plus `-debian`, while
oauth2-proxy uses the source tag unchanged. `docker buildx imagetools inspect` resolves that tag
over the registry API, and the release fails unless the returned manifest digest is the exact
digest that is subsequently scanned and promoted. The registry manifest, derived tag, source
release and immutable reference are stored in `registry-tag-proof-<component>.json`; its SHA-256
is part of the signed release manifest.

The workflow also executes each immutable `linux/amd64` image before authorization. APISIX must
run `apisix version` successfully as UID/GID `636:636` and report the selected release version.
The oauth2-proxy `--help` output must expose every command-line option configured by the runtime,
including the authentication, authorization-header, cookie and session controls. In particular,
this covers `trusted-proxy-ip`, `skip-auth-route`,
`bearer-token-login-fallback`, `extra-jwt-issuers` and `session-store-type`. That bounded output is
retained and hashed into the signed manifest, and the promotion verifier rechecks it. Trivy
independently blocks every detected HIGH or CRITICAL
OS/library vulnerability, a CycloneDX SBOM is generated, and an upstream-review record captures
the contract. A release owner must still review the upstream release notes and source/build
repository relationship. If an upstream project publishes cryptographic provenance in the
future, add its precise identity to the policy; never weaken verification with a wildcard identity
or an `insecure-ignore-*` option.

For each first-party digest the workflow additionally produces BuildKit `mode=max` provenance, a
normalized SLSA provenance predicate, a CycloneDX SBOM, a blocking Trivy SARIF result, a keyless
image signature and signed `cyclonedx` plus `slsaprovenance1` attestations. Detached Sigstore
bundles for the image signature and both attestations are retained as archival copies in the
evidence package as well as uploaded to the registry.

Cosign v3 does not expose a local `--bundle` input on image `verify` or
`verify-attestation`; its source also marks detached-bundle verification for image signatures as
not implemented. Consequently, the promotion gate verifies the exact digest's signature and
attestations from the live registry and transparency log. The signed manifest authenticates the
SHA-256 bytes of each archived bundle, but the current gate does not replay their cryptography and
the evidence tar alone is not an offline image-verification proof. Keep registry artifacts under a
retention policy. If a future Cosign version adds this capability, bind each exact bundle to its
corresponding verification command before claiming offline verification.

## Durable release evidence

After all ten matrix entries pass, the workflow:

1. derives a stable, execution-unique lowercase DNS-label `releaseId` from the commit SHA, workflow
   run ID and run attempt, then hashes every SBOM, SARIF, provenance, upstream-review,
   registry-tag proof and runtime-output file into `release-manifest.json`;
2. signs that manifest as `release-manifest.sigstore.json`;
3. packages the manifest, Sigstore bundle, exact policy and evidence as
   `release-evidence.tar.gz`;
4. uploads the package as a workflow artifact and attaches it to a uniquely tagged GitHub Release.

The GitHub Release avoids relying only on the 90-day workflow-artifact retention. A release can
still be deleted by an administrator; copy the three release assets to the organization's
immutable evidence archive when regulatory retention or disaster recovery requires it.

Retrieve and inspect one release with GitHub CLI:

```bash
tag=archideal-0123456789ab-run-123456789-attempt-1
release_dir="/secure/releases/$tag"
mkdir -p "$release_dir"
gh release download "$tag" \
  --repo Smartappli/ArchiDEAL \
  --pattern release-evidence.tar.gz \
  --dir "$release_dir"
tar -xzf "$release_dir/release-evidence.tar.gz" -C "$release_dir"
jq -r '.releaseId' "$release_dir/release-manifest.json"
jq -r '.images[] | "\(.valuesKey): \(.reference)"' \
  "$release_dir/release-manifest.json"
```

Copy `releaseId` into `RELEASE_ID` and those ten exact references into the production values file.
Do not substitute another release ID or digest, even from the same tag. Both are authenticated by
the same Sigstore-signed manifest.

## Promotion verification

`verify-release.py` runs before render or any `kubectl` call. It fails closed unless all of the
following are true:

- the manifest bundle has the exact trust-root identity and issuer;
- the local Git worktree is clean and its commit, repository workflow, policy hash and set of ten
  images match;
- the values-file `RELEASE_ID` is the exact lowercase DNS-label `releaseId` in the signed manifest;
- every values-file image exactly equals its signed manifest reference and allowlisted repository;
- each evidence file is a regular, non-symlink file with the signed SHA-256, and each retained
  signature/attestation archive has the expected Sigstore bundle structure;
- SBOMs are CycloneDX JSON and HIGH/CRITICAL Trivy SARIF results are empty;
- first-party provenance describes the exact repository, commit, workflow, build context and run;
- all eight first-party registry signatures and both signed attestations verify with Cosign;
- both upstream review records meet their version floor and official release coordinates;
- each approved upstream source tag resolves through the registry to the exact scanned digest;
- the retained APISIX non-root version result and oauth2-proxy security-option help output satisfy
  the policy's runtime contract.

Cosign, transparency services and registry access are mandatory for promotion. There is
deliberately no skip flag. Offline CI and change review remain supported through `render.py`; an
offline render or archived bundle inspection is not a promotion.

Run the gate independently:

```bash
make production-verify \
  PRODUCTION_VALUES=/secure/config/archideal-production-values.yaml \
  PRODUCTION_RELEASE_MANIFEST="$release_dir/release-manifest.json" \
  PRODUCTION_RELEASE_BUNDLE="$release_dir/release-manifest.sigstore.json" \
  PRODUCTION_RELEASE_EVIDENCE_DIR="$release_dir"
```
