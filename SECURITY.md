# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | ✅ Active support  |

Only the latest minor release receives security fixes.  Older major versions
are supported for **90 days** after a new major release is published to PyPI.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

### Option 1 – GitHub Private Security Advisory (preferred)

1. Go to the [Security tab](https://github.com/kobolcs/robot_optimizer_core/security)
   of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the template with as much detail as possible:
   - Affected version(s)
   - Steps to reproduce
   - Potential impact
   - Suggested fix (optional but welcome)

GitHub will keep the report private until a fix is released.

### Option 2 – Email

Send a PGP-encrypted (preferred) or plain-text email to:

```
robot-optimizer-security@users.noreply.github.com
```

Include the word **SECURITY** in the subject line.

## Response Timeline

| Milestone                          | Target time      |
| ---------------------------------- | ---------------- |
| Acknowledgement of report          | Within **48 h**  |
| Initial triage / severity rating   | Within **5 days** |
| Fix available (critical / high)    | Within **14 days** |
| Fix available (medium / low)       | Within **30 days** |
| Public disclosure (after fix)      | Coordinated with reporter |

We follow [responsible disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
Credit will be given in the release notes unless the reporter requests
anonymity.

## Scope

The following are **in scope**:

- Arbitrary code execution via crafted `.robot` / `.resource` files
- Path traversal or file write via the analysis API
- Plugin system sandbox bypass
- Dependency vulnerabilities that affect users of this library

The following are **out of scope**:

- Denial-of-service on intentionally malformed files (best-effort parsing)
- Issues in Robot Framework itself (report to the [RF project](https://github.com/robotframework/robotframework/security))
- Issues in transitive dependencies (report to the upstream project)

## Security Best Practices for Users

- Pin dependency versions in production environments.
- Use `pip audit` or `safety check` as part of your CI pipeline.
- Load third-party plugins only from trusted sources; the built-in
  `SecurePluginManager` performs AST-level validation but is not a
  sandbox replacement.
