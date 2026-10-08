#!/usr/bin/env python3
"""Capture and validate local, definition-bound verification executions."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid

import capture_reviewed_change_set as snapshot

SCHEMA = 1
HEADING = 'Verification Contract'
DIGEST = re.compile(r'[0-9a-f]{64}')
IDENTIFIER = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}')
PURPOSES = {'diagnostic', 'feedback', 'readiness'}
OUTCOMES = {'completed', 'timeout', 'spawn-error', 'interrupted', 'capture-error', 'output-limit', 'abandoned'}
EXCERPT_LIMIT = 16384
OUTPUT_LIMIT = 8 * 1024 * 1024
ARTIFACT_LIMIT = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def shape(value, keys, label):
    require(type(value) is dict and set(value) == set(keys.split()), f'{label}: invalid fields')


def nonempty(value):
    return type(value) is str and bool(value.strip()) and '\x00' not in value


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n').encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    require(type(value) is str and DIGEST.fullmatch(value), 'invalid SHA-256')
    return value


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'unsupported JSON constant: {value}')
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds supported depth') from exc


def relative(value, *, dot=False):
    require(type(value) is str and value and '\x00' not in value and '\\' not in value, 'invalid repository path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and p.as_posix() == value, f'noncanonical/escaping path: {value}')
    require(dot or value != '.', 'root path is not allowed here')
    return value


def safe(root, value, *, dot=False):
    relative(value, dot=dot)
    path = root
    for part in PurePosixPath(value).parts:
        path = path / part
        require(not path.is_symlink(), f'unsupported symlink: {value}')
    return path


def within(path, parent):
    return snapshot.path_is_within(path, parent)


def unit(ledger):
    relative(ledger)
    require(ledger.startswith('notes/epics/') and ledger.endswith('.md'), 'selected ledger must be under notes/epics/')
    return sha(ledger.encode())


def namespace(ledger):
    return f'.deepdone/verification/{unit(ledger)}'


def local_artifact(path):
    return within(path, '.deepdone/verification') or path == '.deepdone/commit-candidate.md' or bool(re.fullmatch(r'\.deepdone/reviews/[^/]+\.json', path))


def evidence_path(path, ledger, roadmap):
    return path == '.git' or path == ledger or path == roadmap or local_artifact(path)


def contract_span(text):
    matches = list(re.finditer(r'^##[ \t]+Verification Contract[ \t]*$', text, re.M))
    require(len(matches) <= 1, 'duplicate verification contract sections')
    if not matches:
        return None
    start = matches[0].end()
    end_match = re.search(r'^##[ \t]+', text[start:], re.M)
    end = start + end_match.start() if end_match else len(text)
    return matches[0].start(), start, end


def read_contract(text, ledger):
    span = contract_span(text)
    require(span is not None, 'missing verification contract; explicitly migrate and run readiness checks')
    body = text[span[1]:span[2]].strip()
    match = re.fullmatch(r'```json\n(.*)\n```', body, re.S)
    require(match is not None, 'verification contract must contain one JSON block')
    value = decode(match[1])
    shape(value, 'schema ledger work_unit inventories attempts', 'verification contract')
    require(type(value['schema']) is int and value['schema'] == SCHEMA, 'unsupported verification contract schema')
    require(value['ledger'] == ledger and value['work_unit'] == unit(ledger), 'verification contract work unit mismatch')
    require(type(value['inventories']) is list and value['inventories'], 'missing inventory revision')
    require(type(value['attempts']) is list, 'attempt index must be an array')
    return value


def render_contract(text, contract):
    block = f'## {HEADING}\n\n```json\n{json.dumps(contract, indent=2)}\n```\n\n'
    span = contract_span(text)
    return text[:span[0]] + block + text[span[2]:] if span else text.rstrip() + '\n\n' + block


def read_bytes(path):
    require(path.is_file() and not path.is_symlink(), f'unreadable evidence file: {path}')
    require(path.stat().st_size <= ARTIFACT_LIMIT, f'evidence exceeds size limit: {path}')
    return path.read_bytes()


def artifact(root, ledger, reference, category):
    shape(reference, 'path sha256', 'artifact reference')
    digest(reference['sha256'])
    path = relative(reference['path'])
    require(path == f'{namespace(ledger)}/{category}/{reference["sha256"]}.json', 'artifact path/digest mismatch')
    raw = read_bytes(safe(root, path))
    require(sha(raw) == reference['sha256'], f'artifact digest mismatch: {path}')
    return decode(raw)


def immutable(root, ledger, category, value):
    raw = canonical(value)
    require(len(raw) <= ARTIFACT_LIMIT, 'artifact exceeds size limit')
    key = sha(raw)
    rel = f'{namespace(ledger)}/{category}/{key}.json'
    target = safe(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            os.link(temporary, target)
        except FileExistsError:
            require(read_bytes(target) == raw, 'immutable artifact collision')
    finally:
        temporary.unlink()
    return {'path': rel, 'sha256': key}


@contextmanager
def locked(root, ledger):
    require(not (root / '.deepdone/STOP').exists(), '.deepdone/STOP exists')
    path = safe(root, f'{namespace(ledger)}/writer.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('verification writer is already active') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def replace_ledger(root, ledger, expected, contract):
    path = safe(root, ledger)
    raw = render_contract(expected.decode('utf-8'), contract).encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        # ponytail: external editors must not race the final comparison and rename.
        require(path.read_bytes() == expected, 'ledger changed concurrently; preserved edits and completed artifacts')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return raw


def definition(check):
    shape(check, 'id acceptance required argv cwd inputs exclusions env context timeout', 'check definition')
    require(type(check['id']) is str and IDENTIFIER.fullmatch(check['id']), 'invalid check ID')
    require(nonempty(check['acceptance']) and type(check['required']) is bool, 'invalid acceptance/required declaration')
    require(type(check['argv']) is list and check['argv'] and all(nonempty(v) for v in check['argv']), 'argv must be nonempty strings')
    relative(check['cwd'], dot=True)
    require(check['context'] == 'local-files', 'unsupported execution context; only declared local-files commands are supported')
    require(type(check['timeout']) in (int, float) and 0 < check['timeout'] <= 3600, 'timeout must be in (0, 3600] seconds')
    require(type(check['env']) is dict and all(type(k) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) and type(v) is str and '\x00' not in v for k, v in check['env'].items()), 'invalid explicit environment')
    require(type(check['inputs']) is list and check['inputs'], 'missing input scope')
    seen = set()
    for item in check['inputs']:
        shape(item, 'path role', 'input')
        relative(item['path'], dot=True)
        require(item['role'] in ('source', 'local-data'), 'unsupported input role')
        require(item['path'] not in seen, 'duplicate input path')
        seen.add(item['path'])
    require(type(check['exclusions']) is list, 'invalid exclusions')
    seen = set()
    for item in check['exclusions']:
        shape(item, 'path reason', 'exclusion')
        path = relative(item['path'])
        require(nonempty(item['reason']) and path not in seen, 'missing exclusion reason or duplicate exclusion')
        require(any(within(path, i['path']) and path != i['path'] for i in check['inputs']), 'exclusion must be inside a declared root')
        require(not any(within(i['path'], path) for i in check['inputs']), 'exclusion overlaps a designated input')
        seen.add(path)
    return sha(canonical(check))


def inventory(root, ledger, contract):
    revisions = []
    definitions = {}
    for number, ref in enumerate(contract['inventories'], 1):
        obj = artifact(root, ledger, ref, 'inventories')
        shape(obj, 'schema work_unit ledger revision reason roadmap checks', 'inventory')
        require(type(obj['schema']) is int and obj['schema'] == SCHEMA and obj['work_unit'] == unit(ledger) and obj['ledger'] == ledger, 'inventory identity mismatch')
        require(type(obj['revision']) is int and obj['revision'] == number and nonempty(obj['reason']), 'invalid inventory revision/reason')
        require(obj['roadmap'] in (None, 'notes/roadmap.md'), 'unsupported roadmap path')
        require(type(obj['checks']) is list and obj['checks'], 'empty inventory')
        ids = set()
        for check in obj['checks']:
            key = definition(check)
            require(check['id'] not in ids, 'duplicate check ID')
            ids.add(check['id'])
            definitions[(check['id'], key)] = (check, obj['roadmap'])
        require(any(c['required'] for c in obj['checks']), 'empty required-check set')
        revisions.append(obj)
    return revisions[-1], definitions


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def environment(check):
    return {'PATH': os.defpath, **check['env']}


def executable(root, check):
    argv0 = check['argv'][0]
    if '/' in argv0:
        path = Path(argv0) if Path(argv0).is_absolute() else root / check['cwd'] / argv0
    else:
        found = shutil.which(argv0, path=environment(check)['PATH'])
        if found is None:
            raise FileNotFoundError(f'executable unavailable: {argv0}')
        path = Path(found)
    path = path.resolve(strict=True)
    require(path.is_file() and os.access(path, os.X_OK), 'executable is not runnable')
    return {'path': str(path), 'sha256': file_digest(path)}


def fingerprint(root, ledger, check, roadmap):
    found = {}
    excludes = [i['path'] for i in check['exclusions']]
    staged = snapshot.run(['git', 'ls-files', '--stage', '-z'], root, binary=True)
    require(staged.returncode == 0, 'cannot classify submodules')
    submodules = {os.fsdecode(row.split(b'\t', 1)[1]) for row in staged.stdout.split(b'\0') if row.startswith(b'160000 ')}
    def visit(rel, role):
        if evidence_path(rel, ledger, roadmap) or any(within(rel, ex) for ex in excludes):
            return
        require(rel not in submodules, f'unsupported submodule input: {rel}')
        path = safe(root, rel, dot=True)
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            require(not (path / '.git').exists() or rel == '.', f'unsupported submodule/nested repository: {rel}')
            entry = {'path': rel, 'kind': 'directory', 'mode': '', 'sha256': '', 'role': role}
        else:
            require(stat.S_ISREG(mode), f'unsupported special input: {rel}')
            entry = {'path': rel, 'kind': 'file', 'mode': '100755' if mode & 0o111 else '100644', 'sha256': file_digest(path), 'role': role}
        if rel in found:
            require(found[rel] == entry, f'conflicting input roles: {rel}')
        if rel not in ('.deepdone', '.deepdone/reviews'):
            found[rel] = entry
        if entry['kind'] == 'directory':
            for child in sorted(path.iterdir()):
                visit(child.relative_to(root).as_posix(), role)
    for item in check['inputs']:
        rel = item['path']
        require(not evidence_path(rel, ledger, roadmap), f'evidence path cannot be a declared input: {rel}')
        visit(rel, item['role'])
    entries = sorted(found.values(), key=lambda e: e['path'])
    require(any(e['kind'] == 'file' for e in entries), 'input scope contains no files')
    return {'sha256': sha(canonical(entries)), 'entries': entries}


def git_context(root):
    head = snapshot.run(['git', 'rev-parse', 'HEAD'], root)
    require(head.returncode == 0, 'cannot read HEAD')
    result = snapshot.run(['git', 'rev-parse', '--git-path', 'index'], root)
    require(result.returncode == 0, 'cannot locate real index')
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return {'head': head.stdout.strip(), 'index_sha256': sha(path.read_bytes()) if path.exists() else None}


def kill_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # ponytail: restricted hosts may allow killing only the direct child.
        process.kill()


def stream_command(root, check):
    output = {name: {'bytes': 0, 'sha256': '', 'excerpt': '', 'truncated': False, 'complete': True} for name in ('stdout', 'stderr')}
    hashes = {name: hashlib.sha256() for name in output}
    excerpts = {name: bytearray() for name in output}
    outcome, code, problem = 'completed', None, ''
    process = None
    try:
        process = subprocess.Popen(check['argv'], cwd=safe(root, check['cwd'], dot=True), env=environment(check), stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        deadline = time.monotonic() + check['timeout']
        with selectors.DefaultSelector() as selector:
            for name in output:
                selector.register(getattr(process, name), selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                if time.monotonic() >= deadline:
                    if outcome == 'completed':
                        outcome = 'timeout'
                    kill_group(process)
                    if time.monotonic() >= deadline + 2:
                        for name in output:
                            output[name]['complete'] = False
                        break
                for key, _ in selector.select(0.02):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    output[name]['bytes'] += len(chunk)
                    hashes[name].update(chunk)
                    excerpts[name].extend(chunk[:max(0, EXCERPT_LIMIT - len(excerpts[name]))])
                    if sum(item['bytes'] for item in output.values()) > OUTPUT_LIMIT and outcome == 'completed':
                        outcome = 'output-limit'
                        kill_group(process)
                        deadline = time.monotonic()
            code = process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        outcome = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'spawn-error'
        problem = f'{type(exc).__name__}: {exc}'
        if process is not None:
            kill_group(process)
            process.wait(timeout=2)
        for item in output.values():
            item['complete'] = False
    finally:
        if process is not None:
            process.stdout.close()
            process.stderr.close()
    for name, item in output.items():
        item['sha256'] = hashes[name].hexdigest()
        item['excerpt'] = base64.b64encode(excerpts[name]).decode('ascii')
        item['truncated'] = item['bytes'] > len(excerpts[name])
    return outcome, code, output, problem


def now():
    return datetime.now(timezone.utc).isoformat()


def attempt_identity(attempt):
    return {key: attempt[key] for key in ('sequence', 'id', 'check', 'definition', 'purpose')}


def initialize(root, ledger, checks, reason, roadmap=None):
    root = root.resolve()
    require(nonempty(reason), 'inventory/migration reason required')
    with locked(root, ledger):
        expected = read_bytes(safe(root, ledger))
        text = expected.decode('utf-8')
        if contract_span(text):
            contract = read_contract(text, ledger)
            _, definitions = inventory(root, ledger, contract)
            validate_history(root, ledger, contract, definitions)
        else:
            require(not list((root / namespace(ledger)).glob('inventories/*.json')), 'verification contract was removed; restore it before revising')
            contract = {'schema': SCHEMA, 'work_unit': unit(ledger), 'ledger': ledger, 'inventories': [], 'attempts': []}
        value = {'schema': SCHEMA, 'work_unit': unit(ledger), 'ledger': ledger, 'revision': len(contract['inventories']) + 1, 'reason': reason, 'roadmap': roadmap, 'checks': checks}
        # Validate the declaration before publishing or editing the ledger.
        require(type(checks) is list and checks, 'empty inventory')
        ids = [definition(c) for c in checks]
        require(len({c['id'] for c in checks}) == len(ids) and any(c['required'] for c in checks), 'duplicate IDs or empty required-check set')
        require(roadmap in (None, 'notes/roadmap.md'), 'unsupported roadmap path')
        contract['inventories'].append(immutable(root, ledger, 'inventories', value))
        replace_ledger(root, ledger, expected, contract)


def run_check(root, ledger, check_id, purpose='readiness'):
    root = root.resolve()
    require(purpose in PURPOSES, 'invalid evidence purpose')
    with locked(root, ledger):
        expected = read_bytes(safe(root, ledger))
        contract = read_contract(expected.decode('utf-8'), ledger)
        current, definitions = inventory(root, ledger, contract)
        validate_history(root, ledger, contract, definitions)
        checks = [c for c in current['checks'] if c['id'] == check_id]
        require(len(checks) == 1, f'unknown current check: {check_id}')
        check = checks[0]
        attempt = {'sequence': len(contract['attempts']) + 1, 'id': uuid.uuid4().hex, 'check': check_id, 'definition': definition(check), 'purpose': purpose, 'status': 'pending', 'receipt': None}
        contract['attempts'].append(attempt)
        expected = replace_ledger(root, ledger, expected, contract)
        receipt = {'schema': SCHEMA, 'ledger': ledger, 'work_unit': unit(ledger), **attempt_identity(attempt), 'started': now(), 'ended': '', 'argv': check['argv'], 'cwd': check['cwd'], 'env': environment(check), 'tool': None, 'before': None, 'after': None, 'git_before': None, 'git_after': None, 'outcome': 'capture-error', 'exit_code': None, 'output': None, 'error': ''}
        try:
            receipt['git_before'] = git_context(root)
            receipt['before'] = fingerprint(root, ledger, check, current['roadmap'])
            try:
                receipt['tool'] = executable(root, check)
            except OSError as exc:
                receipt['outcome'] = 'spawn-error'
                receipt['error'] = str(exc)
            require(not (root / '.deepdone/STOP').exists(), '.deepdone/STOP exists before launch')
            receipt['outcome'], receipt['exit_code'], receipt['output'], receipt['error'] = stream_command(root, check)
            receipt['after'] = fingerprint(root, ledger, check, current['roadmap'])
            receipt['git_after'] = git_context(root)
            if receipt['tool'] is not None:
                require(receipt['tool'] == executable(root, check), 'executable changed during check')
        except (OSError, ValueError) as exc:
            receipt['outcome'] = 'capture-error'
            receipt['error'] = str(exc)
        receipt['ended'] = now()
        attempt['receipt'] = immutable(root, ledger, 'receipts', receipt)
        inventory(root, ledger, contract)
        attempt['status'] = 'final'
        replace_ledger(root, ledger, expected, contract)
        return receipt


def abandon(root, ledger, attempt_id, reason):
    require(nonempty(reason), 'abandonment reason required')
    root = root.resolve()
    with locked(root, ledger):
        expected = read_bytes(safe(root, ledger))
        contract = read_contract(expected.decode(), ledger)
        current, definitions = inventory(root, ledger, contract)
        validate_history(root, ledger, contract, definitions)
        matches = [a for a in contract['attempts'] if a['id'] == attempt_id and a['status'] == 'pending']
        require(len(matches) == 1, 'pending attempt not found')
        attempt = matches[0]
        receipt = {'schema': SCHEMA, 'ledger': ledger, 'work_unit': unit(ledger), **attempt_identity(attempt), 'outcome': 'abandoned', 'reason': reason}
        attempt['receipt'] = immutable(root, ledger, 'receipts', receipt)
        attempt['status'] = 'final'
        replace_ledger(root, ledger, expected, contract)


def validate_fingerprint(value):
    shape(value, 'sha256 entries', 'fingerprint')
    digest(value['sha256'])
    require(type(value['entries']) is list and value['entries'], 'empty fingerprint')
    previous = None
    for item in value['entries']:
        shape(item, 'path kind mode sha256 role', 'fingerprint entry')
        relative(item['path'], dot=True)
        require(previous is None or previous < item['path'], 'fingerprint paths must be unique and sorted')
        previous = item['path']
        require(item['role'] in ('source', 'local-data'), 'invalid fingerprint role')
        if item['kind'] == 'file':
            require(item['mode'] in ('100644', '100755'), 'invalid input mode')
            digest(item['sha256'])
        else:
            require(item['kind'] == 'directory' and item['mode'] == item['sha256'] == '', 'invalid input kind')
    require(sha(canonical(value['entries'])) == value['sha256'], 'fingerprint digest mismatch')


def validate_history(root, ledger, contract, definitions):
    receipts = {}
    ids = set()
    for sequence, attempt in enumerate(contract['attempts'], 1):
        shape(attempt, 'sequence id check definition purpose status receipt', 'attempt')
        require(type(attempt['sequence']) is int and attempt['sequence'] == sequence, 'attempt order mismatch')
        require(type(attempt['id']) is str and re.fullmatch(r'[0-9a-f]{32}', attempt['id']) and attempt['id'] not in ids, 'invalid/duplicate attempt ID')
        ids.add(attempt['id'])
        digest(attempt['definition'])
        require(type(attempt['check']) is str and (attempt['check'], attempt['definition']) in definitions, 'attempt definition not in inventory history')
        require(type(attempt['purpose']) is str and attempt['purpose'] in PURPOSES, 'invalid attempt purpose')
        if attempt['status'] == 'pending':
            require(attempt['receipt'] is None, 'pending attempt has receipt')
            continue
        require(attempt['status'] == 'final', 'invalid attempt status')
        receipt = artifact(root, ledger, attempt['receipt'], 'receipts')
        identity = {'schema': SCHEMA, 'ledger': ledger, 'work_unit': unit(ledger), **attempt_identity(attempt)}
        require(type(receipt) is dict and all(type(receipt.get(k)) is type(v) and receipt.get(k) == v for k, v in identity.items()), 'receipt attempt binding mismatch')
        if receipt.get('outcome') == 'abandoned':
            shape(receipt, 'schema ledger work_unit sequence id check definition purpose outcome reason', 'abandoned receipt')
            require(nonempty(receipt['reason']), 'missing abandonment reason')
        else:
            shape(receipt, 'schema ledger work_unit sequence id check definition purpose started ended argv cwd env tool before after git_before git_after outcome exit_code output error', 'receipt')
            check, _ = definitions[(attempt['check'], attempt['definition'])]
            require(receipt['argv'] == check['argv'] and receipt['cwd'] == check['cwd'] and receipt['env'] == environment(check), 'receipt execution definition mismatch')
            require(type(receipt['outcome']) is str and receipt['outcome'] in OUTCOMES, 'invalid execution outcome')
            require(type(receipt['error']) is str and nonempty(receipt['started']) and nonempty(receipt['ended']), 'invalid execution metadata')
            try:
                start, end = (datetime.fromisoformat(receipt[k]) for k in ('started', 'ended'))
                require(start.tzinfo is not None and end.tzinfo is not None and end >= start, 'invalid execution timestamps')
            except (ValueError, TypeError) as exc:
                raise ValueError('invalid execution timestamps') from exc
            require(receipt['exit_code'] is None or type(receipt['exit_code']) is int, 'invalid process exit code')
            if receipt['outcome'] == 'completed':
                require(type(receipt['exit_code']) is int and all(receipt[k] is not None for k in ('before', 'after', 'tool', 'output', 'git_before', 'git_after')), 'incomplete execution capture')
            for field in ('before', 'after'):
                if receipt[field] is not None:
                    validate_fingerprint(receipt[field])
            if receipt['tool'] is not None:
                shape(receipt['tool'], 'path sha256', 'executable')
                require(type(receipt['tool']['path']) is str and Path(receipt['tool']['path']).is_absolute(), 'invalid executable path')
                digest(receipt['tool']['sha256'])
            for field in ('git_before', 'git_after'):
                if receipt[field] is not None:
                    shape(receipt[field], 'head index_sha256', 'Git context')
                    require(type(receipt[field]['head']) is str and re.fullmatch(r'[0-9a-f]{40,64}', receipt[field]['head']), 'invalid recorded HEAD')
                    if receipt[field]['index_sha256'] is not None:
                        digest(receipt[field]['index_sha256'])
            if receipt['output'] is not None:
                shape(receipt['output'], 'stdout stderr', 'output')
                for stream in receipt['output'].values():
                    shape(stream, 'bytes sha256 excerpt truncated complete', 'output stream')
                    require(type(stream['bytes']) is int and stream['bytes'] >= 0 and type(stream['truncated']) is bool and type(stream['complete']) is bool and type(stream['excerpt']) is str, 'invalid output metadata')
                    digest(stream['sha256'])
                    excerpt = base64.b64decode(stream['excerpt'], validate=True)
                    require(len(excerpt) == min(EXCERPT_LIMIT, stream['bytes']) and stream['truncated'] == (len(excerpt) < stream['bytes']), 'invalid output excerpt length')
                    if not stream['truncated']:
                        require(sha(excerpt) == stream['sha256'], 'output digest mismatch')
        receipts[attempt['id']] = receipt
    return receipts


def ownership(root, ledger, roadmap, check, current, owned):
    tracked = snapshot.run(['git', 'ls-files', '-z'], root, binary=True)
    ignored = snapshot.run(['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '-z'], root, binary=True)
    require(tracked.returncode == ignored.returncode == 0, 'cannot classify verification input ownership')
    tracked_set = {os.fsdecode(p) for p in tracked.stdout.split(b'\0') if p}
    ignored_set = {os.fsdecode(p) for p in ignored.stdout.split(b'\0') if p}
    local = {e['path'] for e in current['entries'] if e['kind'] == 'file' and e['role'] == 'local-data'}
    for entry in current['entries']:
        if entry['kind'] != 'file':
            continue
        path = entry['path']
        if path in local:
            require(path in ignored_set and path not in tracked_set, f'local-data input must be ignored and untracked: {path}')
        else:
            require(path not in ignored_set, f'ignored source input cannot be committed: {path}')
    for record in snapshot.parse_status(root):
        for path in {record.path, record.old_path} - {None}:
            relevant = any(within(path, i['path']) for i in check['inputs']) and not any(within(path, e['path']) for e in check['exclusions'])
            if relevant and path not in local and not evidence_path(path, ledger, roadmap):
                require(path in owned, f'verified input outside reviewed ownership: {path}')


def validate(root, ledger, *, text=None, owned=None):
    root = root.resolve()
    try:
        text = text if text is not None else read_bytes(safe(root, ledger)).decode('utf-8')
        contract = read_contract(text, ledger)
        current, definitions = inventory(root, ledger, contract)
        receipts = validate_history(root, ledger, contract, definitions)
        errors = [f'pending verification attempt: {a["check"]}/{a["id"]}' for a in contract['attempts'] if a['status'] == 'pending']
        for check in current['checks']:
            if not check['required']:
                continue
            key = definition(check)
            attempts = [a for a in contract['attempts'] if a['check'] == check['id'] and a['definition'] == key and a['purpose'] == 'readiness']
            if not attempts:
                errors.append(f'{check["id"]}: missing readiness attempt')
                continue
            latest = attempts[-1]
            if latest['status'] == 'pending':
                continue
            receipt = receipts[latest['id']]
            if receipt['outcome'] != 'completed' or receipt['exit_code'] != 0:
                errors.append(f'{check["id"]}: latest readiness outcome {receipt["outcome"]}, exit {receipt.get("exit_code")}')
                continue
            try:
                require(not receipt['error'] and all(s['complete'] for s in receipt['output'].values()), 'incomplete output capture')
                require(receipt['git_before'] == receipt['git_after'], 'check changed HEAD or real index')
                require(receipt['before'] == receipt['after'], 'inputs changed during execution')
                actual = fingerprint(root, ledger, check, current['roadmap'])
                require(actual == receipt['after'], 'stale verification inputs')
                require(executable(root, check) == receipt['tool'], 'stale executable context')
                if owned is not None:
                    ownership(root, ledger, current["roadmap"], check, actual, owned)
            except (OSError, ValueError) as exc:
                errors.append(f'{check["id"]}: {exc}')
        return errors
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f'verification contract: {exc}']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'run', 'abandon', 'check'))
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--inventory', help='JSON array of check definitions for init')
    parser.add_argument('--reason')
    parser.add_argument('--roadmap', choices=('notes/roadmap.md',))
    parser.add_argument('--check-id')
    parser.add_argument('--purpose', choices=sorted(PURPOSES), default='readiness')
    parser.add_argument('--attempt-id')
    args = parser.parse_args()
    try:
        root = snapshot.git_root(Path.cwd())
        if args.action == 'init':
            require(args.inventory is not None, '--inventory is required')
            initialize(root, args.ledger, decode(read_bytes(Path(args.inventory))), args.reason, args.roadmap)
        elif args.action == 'run':
            receipt = run_check(root, args.ledger, args.check_id, args.purpose)
            print(json.dumps({'attempt': receipt['id'], 'outcome': receipt['outcome'], 'exit_code': receipt['exit_code']}))
            return 0 if receipt['outcome'] == 'completed' and receipt['exit_code'] == 0 and receipt['before'] == receipt['after'] and receipt['git_before'] == receipt['git_after'] else 2
        elif args.action == 'abandon':
            abandon(root, args.ledger, args.attempt_id, args.reason)
        else:
            errors = validate(root, args.ledger)
            print(json.dumps({'errors': errors}))
            return 2 if errors else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'Refusing verification: {exc}')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
