# Development, Commit, and Versioning Rules for AI Agents

## 1. Organization

- When this file is loaded from the Codex home directory, first inspect the
  project root for `AGENTS.md`. If it exists, follow the project's instructions;
  do not overwrite or merge this template into that file. The remaining sections
  of this global file are fallback rules, not additional project requirements.
- If the project has no `AGENTS.md`, copy this file from the Codex home directory
  to the project root and follow the resulting project instructions. Use
  `CODEX_HOME` when configured, otherwise the user's `.codex` directory.
- When this file is the project's own `AGENTS.md`, apply all its sections.
- If the project contains a `versioning.ps1` file, delete it and follow the
  project's `AGENTS.md` commit instructions. Do not execute the legacy script.
  Keep its deletion within the normal commit review and approval process.
- These rules are independent of the programming language, framework, and hosting.

## 2. Mandatory Commit Approval

- EVERY commit requires explicit user approval before execution, regardless of
  approval settings in the application, project, or automation tools.
- Before requesting approval, prepare and present the complete step: the exact
  commit message, included files, a description of each file's changes, and,
  when applicable, the proposed version and changelog entry.
- Wait for approval of that specific commit. Implementation requests, general
  authorization, and approval of previous commits do not replace this approval.
- If the proposed content, files, message, or version change after approval,
  present the updated proposal and obtain approval again.
- This rule also applies to version, changelog, merge, and amend commits and
  commits created by scripts or tools. Never bypass approval through automation.

## 3. Commit Messages and Types

Always write commit messages in English using this format:

```text
[commit type] - Simple message describing what was done
```

Use a short, concrete description consistent with the included changes.
Write the commit body in English as well.

| Type | Purpose |
| --- | --- |
| `initial commit` | First commit in a repository without history |
| `feature` | New or improved functionality |
| `bugfix` | Correction of a problem |
| `release` | Preparation of a new major version |
| `build` | Dependencies, build, or packaging changes |
| `docs` | Documentation or instruction changes |

## 4. Commits in Steps

- Divide work into coherent steps, each with its own description and only the
  files relevant to that change.
- A step may contain several related files. Do not mix independent changes or
  include user changes outside the presented step.
- Review the diff and existing staged files before proposing each commit.
  Stage explicit paths and verify the staged content.
- Describe the changes in each file when requesting approval. When necessary,
  include these details in the commit body, preserving the required first line.
- Run relevant checks and report their results before approval. If a command
  fails, stop the step and resolve the failure before proceeding.

## 5. Version Generation

Every `bugfix`, `feature`, or `release` commit must generate a new version and
record its changes in `CHANGELOG.md`.

Use `MAJOR.MINOR.PATCH` with the increments from the original workflow:

| Commit type | Increment | Example |
| --- | --- | --- |
| `bugfix` | Patch | `1.2.3` → `1.2.4` |
| `feature` | Minor, resetting patch | `1.2.3` → `1.3.0` |
| `release` | Major, resetting minor and patch | `1.2.3` → `2.0.0` |

- Check the current version in version files and repository tags. Resolve any
  discrepancies before proposing the next version. Without a previous version,
  use `0.0.0` as the base for the corresponding increment.
- The initial version `0.0.1` from the original workflow may be prepared when
  the user requests versioning initialization.
- Update the version files and lockfiles applicable to the project's technology
  consistently. Do not create files for unrelated technologies.
- Include version and changelog updates in the same commit step that generated
  them so all files are reviewed and approved together. Do not create additional
  commits without specific approval.
- After the approved commit, create its `vMAJOR.MINOR.PATCH` tag only if tag
  creation was included in the approved proposal. Never overwrite existing tags.
- `initial commit`, `build`, and `docs` do not generate versions automatically.

## 6. Changelog

- Create `CHANGELOG.md` at the project root if it does not exist.
- Keep one `# Changelog` heading at the top and list the newest versions first,
  preserving previous history.
- Label each section `## vMAJOR.MINOR.PATCH - YYYY-MM-DD`, using the local date
  when preparing the version.
- Write simple English notes describing additions, fixes, or changes consistent
  with the submitted step. Do not invent changes.

## 7. Publication

- Commit approval does not automatically authorize push or deployment.
- Publish only when the user authorizes that step and report the actual result.
  Do not confuse a successful Git push with a completed deployment.

## 8. Context Boundaries and Single Responsibility

- The project MUST be separated into business or feature contexts, represented
  by folders or files with explicit boundaries. Apply this organization from
  the beginning, including in small projects.
- Under no circumstances may a file assume responsibilities beyond what its
  name represents. Apply the same principle to folders, modules, classes,
  functions, and components: names and contents must describe the same scope.
- Before adding code, identify its context and responsibility. If the change
  exceeds the destination file's scope, extract that responsibility into a
  specifically named file in the appropriate context. Do not broaden a name
  to justify accumulating responsibilities.
- For example, an authentication file must not calculate prices; a header
  component must not load orders or persist preferences. It may compose or
  call the modules responsible for those operations.
- Entry and composition files must only initialize and connect contexts. Names
  such as `App`, `main`, `index`, `manager`, `service`, or `utils` do not permit
  concentrating business rules from different contexts.
- Keep elements of the same context together and expose only the contracts
  other contexts need. Do not access another module's internals or introduce
  circular dependencies.
- Separate business logic, presentation, and infrastructure as those
  responsibilities arise. Business rules must not depend on UI components,
  HTTP transport, or database implementation details.
- Share code across contexts only when a common responsibility is demonstrated.
  Avoid generic folders that accumulate unrelated functions.
- When changing a file that already violates these boundaries, extract the
  responsibilities involved before adding behavior. Report unrelated problems
  without turning the task into a general rewrite.
- Evaluate separation by cohesion and reasons to change, not an arbitrary line
  count. Avoid both files that do everything and artificial fragmentation.

## 9. Clarity, Contracts, and Maintainability

- Prefer modular, maintainable code and the simplest solution that meets current
  requirements. Do not introduce layers, patterns, configurations, or abstractions
  for hypothetical needs.
- Use descriptive domain names for files, classes, functions, and variables,
  consistent with project naming conventions. Avoid obscure abbreviations,
  magic values, and conditions that are difficult to interpret.
- Keep functions and components small and focused on one task. Reduce nesting, make
  inputs and outputs clear, and avoid hidden side effects.
- Centralize the same business rule to prevent divergent implementations.
  Do not merge rules from different contexts merely because code looks similar.
- Avoid duplicated code when it represents the same responsibility. Reuse or
  extract cohesive behavior without introducing unnecessary abstractions.
- Define explicit data and public interface contracts using the language's
  typing or validation facilities. Validate inputs at system boundaries and
  make invalid states identifiable.
- Keep state in the smallest necessary scope and avoid duplicate sources of
  truth. Prefer predictable transformations and explicit dependencies.
- Handle errors where they can be resolved or presented appropriately. Do not
  silence failures, return false success, or catch exceptions without purpose.
- Use comments to explain decisions, constraints, and reasons. Keep behavior
  understandable from the code. Update contract documentation and remove code
  made obsolete by the change.

## 10. Security, Resources, and User Experience

- Never commit secrets or expose credentials or sensitive data in logs, error
  messages, or client-delivered code.
- Treat external data as untrusted. Use safe APIs for queries, commands, and
  rendering. Enforce authorization at trusted boundaries when access control
  exists. Client validation does not replace server validation.
- Add dependencies only when necessary, considering maintenance, compatibility,
  licensing, and impact. Keep manifests and lockfiles consistent.
- Release resources, subscriptions, and listeners. Handle asynchronous failures
  and concurrency; use cancellation and time limits where relevant.
- For interfaces, use semantic elements, accessible names, visible focus, and
  keyboard navigation. Account for different screens and loading, empty, and
  error states as required by the functionality.
- Avoid unnecessary repeated work and resource access. Measure performance
  problems before introducing optimizations that increase complexity.

## 11. Verification

- Before finishing, check that every changed file remains faithful to its name
  and context, contracts remain consistent, and there are no circular
  dependencies or mixed responsibilities.
- Test observable behavior and relevant rules, including failure and boundary
  cases proportional to risk. For bug fixes, add a regression test when there
  is a reproducible scenario and useful automated coverage.
- Avoid tests that merely mirror implementation, internal details, or trivial
  changes without significant risk.
- Run tests, static analysis, formatting checks, and builds applicable to the
  change using existing project tools. Do not claim checks you did not run;
  report limitations and remaining failures.
- Explicitly list relevant tests that could not be executed, explain why, and
  describe the resulting validation gap.

## 12. Language

- Write all code, variable names, functions, classes, file names, comments,
  docstrings, and documentation in English, including this file and changelogs.
- Communicate with the developer in Brazilian Portuguese, including progress
  updates, explanations, and approval requests. Preserve English text when
  presenting proposed commit messages or documentation excerpts.
- Write all Git commit messages, including their bodies, in English.

## 13. Existing Architecture

- Follow the existing project architecture and established conventions while
  preserving the context boundaries and single-responsibility rules above.
- Inspect the relevant contexts and integration points before implementing a
  change. Extend existing modules and contracts when their responsibilities fit.
- Do not introduce a competing architecture or reorganize unrelated contexts
  within a feature or bug fix. If the current structure conflicts with these
  rules, make the smallest necessary extraction in the affected context and
  explain the decision to the developer.

## 14. Language-Specific Code Quality

- For Python, follow PEP 8 and the project's configured formatter and linter.
  Prefer type hints for function parameters, return values, and data contracts.
- For JavaScript and TypeScript, follow the project's configured formatter and
  linter. Reuse existing configuration rather than introducing competing tools
  or unrelated formatting changes.
- For TypeScript, prefer strict typing. Avoid implicit or unjustified `any`,
  unsafe assertions, and suppression of type errors. Narrow uncertain values
  before use and preserve existing strict compiler settings. When enabling
  strictness in an existing project requires a broader migration, explain and
  scope that migration separately rather than changing unrelated files.
- Apply language-specific rules only where that language is present; they do
  not require adopting a language or adding tools to unrelated projects.

## 15. Implementation Workflow

- Inspect the existing directory structure, applicable instructions, relevant
  files, and tool configuration before modifying files. Identify the affected
  context and follow its established patterns.
- Explain significant architectural changes to the developer, including the
  reason, affected boundaries, and important tradeoffs.
- Modify only files necessary for the requested change and its validation.
  Preserve unrelated user changes; do not perform opportunistic refactoring,
  renaming, dependency updates, or repository-wide formatting.
- Prefer simple solutions over unnecessary complexity, and verify the affected
  behavior with relevant tests whenever possible. Follow the verification and
  reporting requirements above, including reporting tests that could not run.

## 16. Default Development Branch

- Always work, make changes, create commits, and push on `develop` by default.
  Check the current branch before editing files, committing, or pushing.
- If a local `develop` branch exists, switch to it before starting work. If it
  exists only on the intended remote, create a local tracking branch from it.
- If `develop` does not exist locally or on the intended remote, create it from
  the repository's main or default branch before making changes. For a new
  repository without commits, use `develop` as the initial branch.
- Preserve existing uncommitted work when switching branches. Do not discard
  changes, reset history, or overwrite an existing branch to enforce this rule.
  Resolve any blocking branch or base ambiguity with the developer first.
- Push explicitly to `develop` on the intended remote, setting its upstream
  when necessary. Do not rely on an upstream that points to `main`.
- Change `main` only when the developer explicitly requests it for the current
  task. This includes direct edits, commits, merges, rebases, resets, and pushes
  targeting `main`. A general request to implement, commit, push, or deploy
  does not authorize changing `main`.
- Creating or selecting `develop` does not waive commit approval requirements
  or independently authorize a push or deployment.
- This policy belongs to the global template for projects that adopt it. An
  existing project `AGENTS.md` remains authoritative under section 1; do not
  inject this policy into such a project without an explicit request.
