# Security policy

## Reporting a vulnerability

Please report security issues **privately**. Use GitHub's private vulnerability
reporting: open the [Security tab](https://github.com/SomilAgg123/agentifyapi/security)
and choose "Report a vulnerability". That opens a draft advisory visible only to
the maintainers. Please don't file a public issue or discussion for a security problem.

If you can't use GitHub's form, email the maintainer (see the GitHub profile of
[SomilAgg123](https://github.com/SomilAgg123)) with "agentifyapi security" in the subject.

## What to include

- What an attacker can do and what they need first (network access, an API key, a tool name).
- The affected version (`agentifyapi --version` or the git tag) and Python version.
- A minimal reproduction if you have one.

## What to expect

You'll get an acknowledgement within 7 days and a fix or a reasoned rejection within 30 days.
We'll coordinate a release and credit you in the advisory if you want.

## Scope

In scope: the gateway, the registry, the admin UI, policy enforcement, PII redaction, and the
crawler. The demo services under `examples/` are intentionally insecure mock data and are out of scope.

## Defaults worth knowing

Tools are disabled until an owner approves and enables them. Callers are denied unless a policy
rule matches (unless `allow_anonymous: true`, which is for local development only). The admin UI
has no authentication of its own in this version, so don't expose `/admin` or `/mcp-admin` on a
public network.
