# GitHub Copilot instructions

Read and follow the repository-level [`AGENTS.md`](../AGENTS.md) before
analyzing or changing this project. Treat it as the canonical source for the
package structure, supported tooling, architectural boundaries, tests, and
pull request conventions.

When reviewing a pull request, load and follow the
[`code-review` skill](skills/code-review/SKILL.md). Apply it to every changed
file and use the pull request's head branch as the source of repository
instructions.

Use Brazilian Portuguese for review summaries, findings, and explanations.
Keep code identifiers, paths, commands, protocol terms, and quoted text in
their original form.

Prioritize concrete defects in correctness, security, public compatibility,
and tests. In particular, scrutinize OAuth 2.0 and OpenID Connect validation,
JWT and JWKS handling, redirects, cookies, secrets, PKCE, nonce, state,
authorization codes, framework boundaries, and FakeGov isolation.

Report only issues introduced by the pull request or made materially worse by
it. Tie every finding to evidence and a credible execution path. Do not turn
style preferences, speculative risks, generic praise, or unrelated existing
debt into review findings.

Never claim that a command, test, check, or file review succeeded unless it was
actually performed and its result was observed. Do not expose credentials,
tokens, keys, decrypted state, personal data, or other sensitive values in
review output.
