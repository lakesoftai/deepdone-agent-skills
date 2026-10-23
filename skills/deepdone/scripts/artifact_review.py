#!/usr/bin/env python3
"""Artifact-only milestone evidence, reusing local-data verification receipts."""
from __future__ import annotations

import re

import work_unit as w
import verification as v
import capture_reviewed_change_set as s

SCHEMA = 3


def declaration(value):
    v.shape(value, 'roots checks source_scope', 'artifact declaration')
    for key in ('roots', 'checks'):
        values = value[key]
        w.require(type(values) is list and values and all(w.nonempty(p) for p in values),
                  f'artifact declaration requires nonempty {key}')
        w.require(len(set(values)) == len(values), f'duplicate artifact {key}')
    for path in value['roots']:
        v.relative(path)
    value['source_scope'] = w.scope(value['source_scope'])
    return value


def rows(record):
    # Leave legacy epics without typed milestones on their existing parser path.
    if record['kind'] != 'epic' or not re.search(
            r'^\s+- (?:type|artifacts):', w.section(record['text'], 'Milestones'), re.M):
        return []
    return w.milestones(record['text'])


def private_path(root, path):
    v.safe(root, path.rstrip('/'))
    tracked = s.run(['git', 'ls-files', '-z', '--', s.literal_pathspec(path.rstrip('/'))], root)
    ignored = s.run(['git', 'check-ignore', '-q', '--', path], root)
    w.require(tracked.returncode == 0 and not tracked.stdout and ignored.returncode == 0,
              f'artifact evidence must be ignored and untracked: {path}')


def private_storage(root, record):
    if not any(row['type'] == 'artifact-only' for row in rows(record)):
        return
    for path in (record['path'], '.deepdone/reviews/', v.namespace(record['path']) + '/'):
        private_path(root, path)
    if record['roadmap']:
        private_path(root, record['roadmap'])


def bind_checks(record, checks):
    for row in rows(record):
        if row['type'] != 'artifact-only' or row['marker'] != 'x':
            continue
        declared = row['artifacts']
        selected = [c for c in checks if c['id'] in declared['checks'] and c['required']]
        w.require({c['id'] for c in selected} == set(declared['checks']),
                  f'{row["title"]}: completed artifact checks must remain required')
        w.require(any(c['acceptance'] == row['acceptance'] for c in selected),
                  f'{row["title"]}: required check must bind milestone acceptance exactly')
        for path in declared['roots']:
            w.require(any({'path': path, 'role': 'local-data'} in c['inputs'] and
                          not any(v.within(e['path'], path) or v.within(path, e['path'])
                                  for e in c['exclusions']) for c in selected),
                      f'{row["title"]}: artifact root needs a required local-data check without exclusions: {path}')


def inventory(root, record, row):
    check = {'inputs': [{'path': p, 'role': 'local-data'} for p in row['artifacts']['roots']],
             'exclusions': []}
    result = v.fingerprint(root, record['path'], check, record['roadmap'])
    v.ownership(root, record['path'], record['roadmap'], check, result, set())
    return result


def source_guard(root, record, row):
    """Compare declared source with HEAD even when Git status flags hide edits."""
    scope = row['artifacts']['source_scope']
    # Artifact roots are local data; all remaining declared source must match HEAD.
    check = {'inputs': [{'path': p, 'role': 'source'} for p in scope['include']],
             'exclusions': [{'path': p} for p in scope['exclude'] + row['artifacts']['roots']]}
    current = v.fingerprint(root, record['path'], check, record['roadmap'], allow_empty=True)
    try:
        v.ownership(root, record['path'], record['roadmap'], check, current, set())
    except ValueError as exc:
        raise ValueError(f'artifact-only milestone has source changes or unrepresentable source; use the code review/commit path: {exc}') from exc
    # Catch staged-only changes that are absent from the worktree projection.
    selected = s.select_reviewed_records(s.parse_status(root), scope['include'], scope['exclude'],
                                        {record['path'], record['roadmap']}, record['path'])
    w.require(not selected, 'artifact-only milestone has Git changes in source scope; use the code review/commit path')
    return current


def selected(record, entry):
    import commit_progress
    w.require(entry.get('type') == 'artifact-only', 'artifact review requires type: artifact-only')
    matches = [r for r in rows(record) if r['title'] == entry.get('milestone')]
    w.require(len(matches) == 1 and matches[0]['type'] == 'artifact-only' and matches[0]['marker'] == 'x',
              'artifact review must name an explicitly completed artifact-only milestone')
    row = matches[0]
    w.require(w.scope(entry['scope']) == row['artifacts']['source_scope'], 'artifact Review source scope differs from milestone declaration')
    w.require(w.nonempty(entry.get('notes')) and entry.get('disposition') == 'accepted',
              'artifact review requires reviewer findings in notes and disposition: accepted')
    w.require(not commit_progress.review_has_blocker(['notes: ' + entry['notes']]) and
              not commit_progress.blocking_open_loops(w.section(record['text'], 'Open Loops').splitlines()),
              'artifact review has unresolved findings or open loops')
    # This route cannot replace the cumulative code snapshot of an earlier slice.
    w.require(not any(r['type'] == 'code' and r['marker'] == 'x' for r in rows(record)),
              'epic contains completed code milestones; retain the cumulative code snapshot and commit path')
    return row


def capture(root, record, entry, identity):
    review_id, base, manifest_rel, include, exclude, evidence_roles = identity
    row = selected(record, entry)
    private_storage(root, record)
    source_guard(root, record, row)
    errors = v.validate(root, record['path'], text=record['text'], owned=set(), tree='HEAD')
    w.require(not errors, '; '.join(errors))
    manifest = {'schema_version': SCHEMA, 'kind': 'artifact-only', 'review_id': review_id,
                'ledger_path': record['path'], 'base_head': base, 'milestone': row['title'],
                'scope': {'include': include, 'exclude': exclude},
                'artifacts': inventory(root, record, row),
                'evidence': [s.filesystem_evidence(root, role, path) for role, path in sorted(evidence_roles.items())]}
    path = root / manifest_rel
    private_path(root, manifest_rel)
    w.require(not s.ref_oid(root, s.review_ref(root, review_id)), 'artifact review ID already has a Git snapshot; use a fresh review ID')
    s.write_manifest_atomic(path, manifest)
    return path


def validate(root, record, entry, manifest):
    from check_reviewed_change_set import validate_evidence
    row = selected(record, entry)
    identity = s.validate_entry(root, record['path'], entry)
    v.shape(manifest, 'schema_version kind review_id ledger_path base_head milestone scope artifacts evidence', 'artifact review manifest')
    w.require(type(manifest['schema_version']) is int and manifest['schema_version'] == SCHEMA and
              manifest['kind'] == 'artifact-only' and manifest['review_id'] == identity[0] and
              manifest['base_head'] == identity[1] and manifest['ledger_path'] == record['path'] and
              manifest['milestone'] == row['title'], 'artifact review manifest identity mismatch')
    private_storage(root, record)
    private_path(root, identity[2])
    s.validate_manifest_binding(root, record['path'], entry, manifest)
    validate_evidence(root, manifest)
    w.require(inventory(root, record, row) == manifest['artifacts'], 'reviewed artifact inventory changed')
    source_guard(root, record, row)
    errors = v.validate(root, record['path'], text=record['text'], owned=set(), tree='HEAD')
    w.require(not errors, '; '.join(errors))
