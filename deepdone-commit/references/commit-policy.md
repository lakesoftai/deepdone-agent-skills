# DeepDone Commit Policy

## Candidate When Unclear

Default to a commit candidate only when intent is unclear.

Commit automatically when the current request or DeepDone supervisor mode authorizes commit (`until-commit`, `end-to-end`, `ready_to_commit`, or explicit commit request). Do not ask for a second confirmation.

## No Push

Never push by default.

## No Blind Staging

Do not use `git add .`.

Use `git status --short --untracked-files=all`, not plain short status, before staging. Plain short status can collapse untracked directories and make `git add -- <dir>` stage local files by accident.

Stage exact files after checking:

- expected path,
- no secrets,
- no local-only artifacts,
- no unrelated modifications.

Expected untracked files are valid commit inputs. Stage them by exact path. Do not require a second user approval just because a file is new.

## Gates

Commit only when:

- ledger is current,
- verification is current,
- review has no blocking findings,
- open loops do not block this commit,
- git diff matches the active scope.

If the environment refuses writes to `.git/index`, refs, or other git metadata, stop with that permission error. Do not write git internals directly.
