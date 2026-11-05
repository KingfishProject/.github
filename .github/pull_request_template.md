Closes #

<!--
  Pull requests are squash-merged, and release-please reads the squash
  commit's title, so it decides the version bump and the changelog line.
  GitHub fills that title with this pull request's title only when the
  repository's squash default is "Pull request title"; otherwise check it in
  the merge box. In a repository that still allows merge commits,
  release-please reads each commit on the branch instead, so give every one a
  Conventional Commit message until the repository switches.

      <type>(<optional scope>): <subject>

  feat    something a user can now do        minor bump
  fix     released behavior that was wrong   patch bump
  perf    the same behavior, faster          patch bump
  revert  undoing an earlier change          patch bump
  docs    patch bump where the changelog shows docs (the python release
          type does by default), otherwise no release on its own
  refactor, test, build, ci, style, chore: no release on their own

  Breaking (something that worked stops working for a user or another
  repository: a removed or renamed command, flag, endpoint, field, file path,
  or output format, or a migration that cannot be undone): put ! after the
  type or scope, and when merging, make the squash commit body a
  "BREAKING CHANGE:" paragraph saying what a user must do.

  Subject: lowercase, imperative, no trailing period.
-->

## What changed

<!-- One or two sentences, from the point of view of someone using it. -->

## Why

<!-- Link the issue, spec, or decision behind it. -->

## How it was verified

<!-- Commands run and what they showed, fixtures used, screenshots for site changes. For a Spec Kit feature, the acceptance scenarios covered and how each was checked. -->

## Deploy impact

<!-- New secrets or variables (by name only), bindings, schedules, data migrations, or "none". -->

## Breaking changes

<!-- Only for a breaking change: the old and new names or paths, and what a user has to do. Otherwise delete this section. -->

## Checklist

- [ ] The title is a Conventional Commit whose type matches what ships
- [ ] Breaking? `!` in the title, and the old and new names or paths, and what a user has to do, under Breaking changes
- [ ] Tests added or updated; CI passes
- [ ] No secret, credential, or anything that could identify a confidential source in the code, the logs, or this description
- [ ] In a public repository, no private repository, investigation target, private person's contact details, internal hostname, or IP address named or linked in the title, this description, the commits, or the logs
- [ ] Versions, `CHANGELOG.md`, and `.release-please-manifest.json` untouched (release-please owns them)
