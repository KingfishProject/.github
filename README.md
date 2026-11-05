# .github

Organization-wide automation and defaults for The Kingfish Project: the release credential sync below, and the [default community files](#defaults-for-every-repository) that GitHub uses in every repository without its own.

## Sync release app credentials

Kingfish repositories cut releases with [release-please](https://github.com/googleapis/release-please), authenticated as a GitHub App (the release app) rather than with `GITHUB_TOKEN`. Pull requests opened with `GITHUB_TOKEN` do not trigger CI, and commits the app makes through the API are signed by GitHub.

The release app's client ID is the organization variable `RELEASE_APP_CLIENT_ID`, and its private key is the organization secret `RELEASE_APP_PRIVATE_KEY`. On GitHub Free, organization variables and secrets reach public repositories only. [`sync-release-credentials.yml`](.github/workflows/sync-release-credentials.yml) runs here, in a public repository, and copies both values into each private repository that runs release-please, as a repository variable and a repository secret with the same names. The release workflow in a private repository reads them the same way a public repository does:

```yaml
- uses: actions/create-github-app-token@v3.3.0
  id: app-token
  with:
    client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
    private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
    permission-contents: write
    permission-pull-requests: write
    permission-issues: write
```

### How the values travel

1. **Organization to this workflow.** GitHub Actions hands an organization secret or variable to every workflow run in a repository that the value's **Repository access** setting covers. `RELEASE_APP_CLIENT_ID` and `RELEASE_APP_PRIVATE_KEY` are shared with public repositories, and this repository is public, so its runs receive them as `${{ vars.RELEASE_APP_CLIENT_ID }}` and `${{ secrets.RELEASE_APP_PRIVATE_KEY }}`. No app or token takes part in this step. For the private key, no API could stand in: GitHub's API never returns a secret's value, whatever permissions the caller holds.
2. **This workflow to each private repository.** The workflow mints a sync app token and runs `gh variable set` and `gh secret set` against each repository in scope. This is the only step that uses the sync app, so it needs only the repository permissions Secrets and Variables (write), plus Metadata.
3. **Private repository to its release workflow.** The repository's own release workflow reads the copies as `vars.RELEASE_APP_CLIENT_ID` and `secrets.RELEASE_APP_PRIVATE_KEY` and mints a release app token from them.

### Scope

A private repository is in scope when it is not archived and carries the repository topic `release-please`. Add the topic (on the repository page, the gear next to **About**) to any private repository that releases, before its first release workflow runs. Topics come with the Metadata permission every GitHub App has, so the sync app needs no access to repository contents.

The workflow runs daily, on demand from the Actions tab, and whenever the workflow file changes on `main`. It never deletes a copy. A repository that leaves scope keeps its copies until someone deletes them in that repository's settings.

### Why a second app

Writing another repository's secrets needs the Secrets and Variables permissions. If the release app held them, every private repository that stores its key could mint a token that rewrites secrets in any repository the app is installed on. The sync uses a second GitHub App (the sync app) with only those two permissions, plus the Metadata permission every app has. It holds no organization permissions: the organization's values reach this workflow through the `vars` and `secrets` contexts, never through the app. Its key is stored in this repository alone, and the release app keeps only Contents, Pull requests, and Issues.

### Public logs

This repository's Actions logs are public. The workflow masks the name of every private repository before printing anything, and its summary reports counts only. Anyone editing the workflow has to keep that property: no `set -x`, no step summary or log line that names a repository, and no workflow input that takes a repository name. Client IDs are not secret and can appear in the logs.

## Setup

### 1. Create the sync app

In the organization's settings, open **Developer settings > GitHub Apps > New GitHub App**:

- **Name**: anything recognizable, such as "Kingfish credential sync".
- **Homepage URL**: this repository's URL.
- **Webhook**: clear **Active**. The app receives no events.
- **Repository permissions**:
  - **Secrets**: Read and write
  - **Variables**: Read and write
  - **Metadata**: Read-only (GitHub requires it; it also covers topics)
  - Everything else, including Contents and Issues: No access.
- **Organization permissions**: none. Organization secrets and variables in particular stay at No access.
- **Where can this GitHub App be installed?**: Only on this account.

After creating it, copy the **Client ID**, then generate a private key under **Private keys** (a `.pem` file downloads).

### 2. Install it

From the app's page, choose **Install App**, pick the organization, and select **All repositories**, so new private repositories are covered without another step.

### 3. Store its credentials in this repository only

In this repository's **Settings > Secrets and variables > Actions**:

- Variables tab: `SYNC_APP_CLIENT_ID` = the sync app's client ID.
- Secrets tab: `SYNC_APP_PRIVATE_KEY` = the full contents of the `.pem` file, including the `BEGIN` and `END` lines.

The key has to keep its line breaks. A key whose line breaks turned into spaces, or were dropped, fails in the token step with "DECODER routines::unsupported". A key stored on one line with literal `\n` escapes works, because the token action turns them back into line breaks. Setting the secret from the file avoids the problem:

```sh
gh secret set SYNC_APP_PRIVATE_KEY --repo KingfishProject/.github < path/to/key.pem
```

The organization secret `RELEASE_APP_PRIVATE_KEY` follows the same rule. Setting it from the file, limited to this repository (the sync delivers it everywhere else), needs a `gh` login with the `admin:org` scope (`gh auth refresh -h github.com -s admin:org`):

```sh
gh secret set RELEASE_APP_PRIVATE_KEY --org KingfishProject --visibility selected --repos .github < path/to/release-app-key.pem
```

Do not add the sync app's values at the organization level. Delete the downloaded `.pem` after saving it, or keep it only in 1Password.

### 4. Check the release app and the organization values

The release app needs **Contents**, **Pull requests**, and **Issues** set to Read and write, with no Secrets or Variables permission, and it must be installed on every repository that releases.

In the organization's **Settings > Secrets and variables > Actions**, the **Repository access** of both `RELEASE_APP_CLIENT_ID` (Variables tab) and `RELEASE_APP_PRIVATE_KEY` (Secrets tab) must include this repository: "Public repositories" does, as would "Selected repositories" with `.github` in the list. That setting, not any app permission, is what lets this workflow read them ([How the values travel](#how-the-values-travel)).

### 5. Tag the repositories that release

Add the topic `release-please` to every private repository that runs release-please.

### 6. Run it

Merge the workflow to `main` (that push runs it once), or open **Actions > Sync release app credentials > Run workflow**. The run summary shows how many repositories received the credentials, how many lack the topic, and how many failed. Re-run any release workflow that failed because the credentials were missing.

### Hardening (optional)

The job declares the `release-credentials` environment, which GitHub creates on the first run. To keep the sync key away from workflows on other branches, open **Settings > Environments > release-credentials**, set **Deployment branches and tags** to `main` only, add `SYNC_APP_PRIVATE_KEY` as an environment secret, and delete the repository-level copy.

### When the schedule stops

GitHub turns off a scheduled workflow in a public repository after 60 days without activity, and emails a warning first. A commit pushed before then keeps it on. Once a workflow is off, no event starts it, not even a run by hand, until someone opens it under **Actions** and clicks **Enable workflow**. This applies to the credential sync and to CodeQL.

### Rotating a key

- Release app: generate a new private key, replace the organization secret `RELEASE_APP_PRIVATE_KEY`, run the sync, then delete the old key from the app's settings.
- Sync app: generate a new private key, replace `SYNC_APP_PRIVATE_KEY` here, run the sync to confirm it works, then delete the old key.

## Defaults for every repository

GitHub uses these files in any KingfishProject repository, public or private, that lacks its own file of the same kind:

| File | What it does |
| --- | --- |
| [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/) | Issue forms for a Task, a Bug report, and a Feature. Each sets the issue type, and adds the issue to the organization's project board when the person opening it can write to the board. Blank issues are offered only to people with write access, as an option GitHub labels **Maintainers only**. |
| [`.github/pull_request_template.md`](.github/pull_request_template.md) | The pull request template |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How work is tracked, how pull requests work, and how releases happen |
| [`SECURITY.md`](SECURITY.md) | How to report a security problem privately |
| [`SUPPORT.md`](SUPPORT.md) | Where questions about a repository go, and where readers' questions go |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | The Contributor Covenant 2.1, and where to report a problem |
| [`ACCESSIBILITY.md`](ACCESSIBILITY.md) | The accessibility target, and how to report a barrier |

A repository's own file replaces the default completely; GitHub never combines the two. Issue templates go all together: a repository whose own `.github/ISSUE_TEMPLATE` folder holds any valid issue template or a `config.yml` gets none of these forms and none of this `config.yml`, so it copies any form it still wants. An issue opened through the API or with `gh issue create` never uses a form, so it gets a type and a place on the board only when it sets them itself.

GitHub enforces a form's required fields only in public repositories, so in a private repository any field can arrive empty. A form that sets a label needs that label to exist here and in every repository that uses the form, so these forms set none. Because this repository is public, these files never name a private repository, a person, or anything under investigation. The same holds for [`profile/README.md`](profile/README.md), the organization's public profile on GitHub.

## Checks for this repository

- [`checks.yml`](.github/workflows/checks.yml) runs on every pull request and every push to `main`, in three jobs a ruleset can require: **Workflows** (actionlint, with shellcheck on every `run:` script), **Issue forms** ([`.github/scripts/check_issue_forms.py`](.github/scripts/check_issue_forms.py), which checks the forms against GitHub's documented schema), and **Markdown style** (markdownlint-cli2 with [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc)). It needs no secret.
- [`codeql.yml`](.github/workflows/codeql.yml) runs CodeQL's workflow-security analysis (**Analyze workflows**) on pull requests, on pushes to `main`, and weekly. Its weekly run falls under the same 60-day rule as the credential sync's schedule ([When the schedule stops](#when-the-schedule-stops)); while GitHub has it turned off, pull requests and pushes skip it too, and a security configuration applied in that window could turn on CodeQL's default setup, which rejects this workflow's results.
- [`dependabot.yml`](.github/dependabot.yml) opens one grouped pull request a week for action updates, titled `ci(deps): ...`.
