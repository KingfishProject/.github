# Contributing to Kingfish repositories

This is the default for every repository in the KingfishProject organization that has no `CONTRIBUTING.md` of its own in its `.github` folder, root, or `docs` folder. A repository's own file replaces this one completely, so a repository that needs its own adds what is particular to it and links to [this file](https://github.com/KingfishProject/.github/blob/main/CONTRIBUTING.md) for the rest.

## Tracking work

Every piece of work has an issue. The issue's fields show where it stands:

| Status | How it looks on the issue |
| --- | --- |
| Not started | Open, with no **Start date** |
| In progress | Open, with a **Start date**, an assignee, and, when the work changes files, a draft pull request that says `Closes #N` |
| Done | Closed: by the merged pull request when there is one, otherwise by hand when the work is done |

- Give every issue a type (Task, Bug, or Feature), a **Priority**, and an **Effort**. Set a **Target date** when the work is due by a certain date. If a date slips, change it on the issue and say why in a comment. If **Start date** or **Target date** is missing from an issue's sidebar, add it with **Add field**.
- When work starts, set the **Start date** and assign whoever is doing it.
- Break larger work into sub-issues under one parent issue. GitHub shows the parent's progress from its sub-issues.
- Assign the owner, the person who runs The Kingfish Project, to any issue or pull request that needs their decision, review, or a step only they can take, such as a dashboard setting.
- Issues opened from the organization's Task, Bug report, and Feature forms join the [project board](https://github.com/orgs/KingfishProject/projects/5) when the person opening them can write to the board. Add every other issue to the board yourself: a blank issue, one opened through the API, or one in a repository with forms of its own.
- An issue opened without a form, such as through the API, gets nothing from one. Set its type and fields yourself, add it to the board, and give its body the headings of the matching form. Task: Why, Scope, Acceptance, Depends on. Bug report: What happened, What should happen, Where, How to reproduce. Feature: Problem, Proposal, Acceptance, Depends on. GitHub enforces a form's required fields only in public repositories, so fill them in everywhere.

## Pull requests

- Branch from `main`. Never commit to `main` directly.
- Title the pull request as a [Conventional Commit](https://www.conventionalcommits.org) (`feat:`, `fix:`, `docs:`, `chore:`). Pull requests are squash-merged, and release-please reads the squash commit's title. GitHub fills it with the pull request title only when the repository's squash default is **Pull request title**, so check the title in the merge box. In a repository that still allows merge commits, release-please reads each commit on the branch instead, so give every one a Conventional Commit message until the repository switches.
- Link the issue with `Closes #N`, or `Closes KingfishProject/REPOSITORY#N` when the issue lives in another repository, so merging the pull request closes it. GitHub reads the keyword only in a pull request that targets the default branch. A pull request in a public repository never names an issue in a private one: link the pull request from the private issue instead, and close that issue by hand once the pull request merges.
- Run the repository's own checks before asking for review. CI must pass before a merge; never merge red.
- Keep secrets, credentials, and anything that could identify a confidential source out of code, logs, and descriptions, and name a secret by its variable name only. In a public repository, also keep out the names of private repositories, anything under investigation, private people's contact details, internal hostnames, and IP addresses, in titles, descriptions, commit messages, and logs alike.
- Title a security fix `fix(security): ...`. Never put the details of an unfixed vulnerability in a commit message, and never open a public pull request for one: in a public repository, fix it in a temporary private fork from a draft security advisory.

## Releases

Repositories that release use release-please, which opens a release pull request on `main` once a releasable commit lands and updates it as more land. Merging it tags the version and publishes the GitHub release. Release workflows authenticate as the organization's release app, or are moving to it, and the [README of the organization's `.github` repository](https://github.com/KingfishProject/.github#readme) explains how a private repository gets that app's credentials.

## Security, support, and conduct

- Report a security problem as [SECURITY.md](https://github.com/KingfishProject/.github/blob/main/SECURITY.md) says, never in a public issue.
- [SUPPORT.md](https://github.com/KingfishProject/.github/blob/main/SUPPORT.md) says where questions about a repository go, and where readers send corrections, tips, and requests.
- [CODE_OF_CONDUCT.md](https://github.com/KingfishProject/.github/blob/main/CODE_OF_CONDUCT.md) sets how people treat each other here, and [ACCESSIBILITY.md](https://github.com/KingfishProject/.github/blob/main/ACCESSIBILITY.md) says how to report a barrier.
