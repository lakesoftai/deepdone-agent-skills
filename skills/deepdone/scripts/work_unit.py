#!/usr/bin/env python3
"""Typed durable work records and shared selection, independent of receipt history."""
from __future__ import annotations

import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
import re

TASK_PATH = re.compile(r'\.deepdone/tasks/([a-z0-9][a-z0-9_-]{0,79})\.md')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def section(text, name):
    match = re.search(rf'^##[ \t]+{re.escape(name)}[ \t]*$', text, re.M)
    if not match:
        return ''
    tail = text[match.end():]
    return re.split(r'^##[ \t]+', tail, maxsplit=1, flags=re.M)[0].strip()


def kind(path):
    require(isinstance(path, str) and path and '\\' not in path and '\x00' not in path,
            'invalid work-unit path')
    p = PurePosixPath(path)
    require(not p.is_absolute() and '..' not in p.parts and p.as_posix() == path,
            f'noncanonical work-unit path: {path}')
    if TASK_PATH.fullmatch(path):
        return 'task'
    require(path.startswith('notes/epics/') and path.endswith('.md'),
            'work unit must be a canonical task or notes/epics/ ledger')
    return 'epic'


def identity(path):
    kind(path)
    return hashlib.sha256(path.encode()).hexdigest()


def safe(root, path):
    current = root
    for part in PurePosixPath(path).parts:
        current /= part
        require(not current.is_symlink(), f'unsupported work-unit symlink: {path}')
    return current


def decode(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate Task JSON key: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'unsupported Task JSON constant: {value}')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    except RecursionError as exc:
        raise ValueError('Task JSON nesting exceeds supported depth') from exc


def nonempty(value):
    return type(value) is str and bool(value.strip()) and '\x00' not in value


def scope(value):
    require(type(value) is dict and set(value) == {'include', 'exclude'}, 'invalid task scope fields')
    result = {}
    for key in ('include', 'exclude'):
        roots = value[key]
        require(type(roots) is list and all(nonempty(p) for p in roots), f'invalid task scope {key}')
        normalized = []
        for raw in roots:
            p = raw.strip().strip('`')
            require(not p.startswith('/'), f'unsafe task scope: {raw}')
            p = p.rstrip('/') or '.'
            require(not p.startswith('/') and '..' not in PurePosixPath(p).parts and '\\' not in p,
                    f'unsafe task scope: {raw}')
            normalized.append(posixpath.normpath(p))
        require(len(normalized) == len(set(normalized)), f'duplicate task scope {key}')
        result[key] = sorted(normalized)
    require(result['include'], 'empty task include scope')
    return result


def load(root, path, expected_kind=None, *, text=None):
    record_kind = kind(path)
    require(expected_kind in (None, record_kind), f'{expected_kind} selector cannot select {record_kind}: {path}')
    file = safe(root, path)
    require(file.is_file(), f'missing work-unit record: {path}')
    text = file.read_text(encoding='utf-8') if text is None else text
    title = re.search(r'^#[ \t]+(.+?)\s*$', text, re.M)
    status = section(text, 'Status')
    task = None
    if record_kind == 'task':
        for heading in ('Task', 'Status', 'Review', 'Open Loops', 'Next Action', 'Verification Log'):
            require(len(re.findall(rf'^##[ \t]+{heading}[ \t]*$', text, re.M)) == 1,
                    f'task requires exactly one {heading} section')
        block = re.fullmatch(r'```json\n(.*)\n```', section(text, 'Task'), re.S)
        require(block is not None, 'Task must contain exactly one JSON block')
        task = decode(block[1])
        require(type(task) is dict and set(task) == {'schema', 'kind', 'id', 'goal', 'scope', 'acceptance', 'constraints'},
                'invalid Task fields')
        require(type(task['schema']) is int and task['schema'] == 1, 'unsupported Task schema')
        require(task['kind'] == 'task', 'unsupported Task kind')
        require(task['id'] == TASK_PATH.fullmatch(path)[1], 'task filename-ID mismatch')
        require(nonempty(task['goal']), 'task goal is empty')
        task['scope'] = scope(task['scope'])
        require(type(task['constraints']) is list and all(nonempty(c) for c in task['constraints']), 'invalid task constraints')
        require(type(task['acceptance']) is list and task['acceptance'], 'empty task acceptance')
        ids = set()
        for pair in task['acceptance']:
            require(type(pair) is dict and set(pair) == {'check_id', 'condition'}, 'invalid acceptance pair')
            require(type(pair['check_id']) is str and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}', pair['check_id']), 'invalid acceptance check ID')
            require(pair['check_id'] not in ids, 'duplicate acceptance check ID')
            require(nonempty(pair['condition']), 'empty acceptance condition')
            ids.add(pair['check_id'])
        require(status in ('active', 'blocked', 'complete'), 'unsupported task Status')
        require(nonempty(section(text, 'Next Action')), 'task Next Action is empty')
        require(nonempty(section(text, 'Review')) and nonempty(section(text, 'Open Loops')), 'empty task lifecycle section')
    else:
        values = [re.sub(r'^(?:[-*]\s*)?(?:\[[ x-]\]\s*)?(?:(?:status|state)\s*:\s*)?', '', line.strip().lower()) for line in status.splitlines()]
        status = next((v for v in values if v in ('active', 'in progress', 'in-progress', 'current', 'blocked', 'complete', 'archived')), '')
        if status in ('in progress', 'in-progress', 'current'):
            status = 'active'
    return {'kind': record_kind, 'id': task['id'] if task else PurePosixPath(path).stem,
            'path': path, 'identity': identity(path), 'title': title[1] if title else PurePosixPath(path).stem,
            'status': status, 'roadmap': None if task else ('notes/roadmap.md' if (root / 'notes/roadmap.md').is_file() else None),
            'task': task, 'text': text}


def bind_checks(record, checks, roadmap):
    if record['kind'] != 'task':
        return
    require(roadmap is None, 'task cannot have roadmap association')
    for pair in record['task']['acceptance']:
        matches = [c for c in checks if c['id'] == pair['check_id']]
        require(len(matches) == 1 and matches[0]['required'], f'task acceptance requires current required check: {pair["check_id"]}')
        require(matches[0]['acceptance'] == pair['condition'], f'task acceptance condition mismatch: {pair["check_id"]}')


def bind_review(record, entry):
    if record['kind'] == 'task':
        require(record['status'] == 'complete', 'task Review requires Status complete')
        require(scope(entry.get('scope')) == record['task']['scope'], 'task Review scope mismatch')
        require(entry.get('evidence') == {'ledger': record['path']}, 'task Review requires only selected task evidence')


def review_passed(text):
    review = section(text, 'Review')
    pattern = r'(?:^|[\s`])(?:review-)?result:\s*(pass|fail|blocked|pending)\b' if review else r'(?:^|[\s`])review-result:\s*(pass|fail|blocked|pending)\b'
    results = re.findall(pattern, review or section(text, 'Decisions'), re.I)
    return bool(results and results[-1].lower() == 'pass')


def public(record):
    return {key: record[key] for key in ('kind', 'id', 'path', 'identity', 'title', 'status')} if record else None


def add_selectors(parser, *, required=False):
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument('--task', help='canonical compact task path')
    group.add_argument('--ledger', help='repository-relative epic ledger path')


def explicit(root, args):
    return load(root, args.task if args.task is not None else args.ledger, 'task' if args.task is not None else 'epic')


def select(root, *, task=None, ledger=None):
    if task is not None or ledger is not None:
        try:
            require(task is None or ledger is None, 'task and ledger selectors are mutually exclusive')
            return load(root, task if task is not None else ledger, 'task' if task is not None else 'epic'), 'explicit', []
        except (OSError, ValueError, RecursionError) as exc:
            return None, 'explicit', [{'reason': str(exc), 'paths': [task if task is not None else ledger]}]
    records, errors = {}, []
    pointer = None
    roadmap = root / 'notes/roadmap.md'
    try:
        if roadmap.exists() or roadmap.is_symlink():
            active = section(safe(root, 'notes/roadmap.md').read_text(), 'Active Epic')
            match = re.search(r'^-\s*ledger:\s*(.+?)\s*$', active, re.M)
            require(match is not None, 'broken roadmap: missing active ledger pointer')
            pointer = match[1].strip().strip('`')
            if pointer in ('none', 'null'):
                pointer = None
            if pointer:
                records[pointer] = load(root, pointer, 'epic')
                require(records[pointer]['status'], f'missing epic Status: {pointer}')
                name = re.search(r'^-\s*name:\s*(.+?)\s*$', active, re.M)
                records[pointer]['roadmap_name'] = name[1] if name else records[pointer]['title']
                if re.search(r'^-\s*state:\s*blocked\s*$', active, re.M):
                    records[pointer]['status'] = 'blocked'
    except (OSError, ValueError, RecursionError) as exc:
        errors.append({'reason': str(exc), 'paths': ['notes/roadmap.md', *([pointer] if pointer else [])]})
    for directory in ('notes/epics', '.deepdone/tasks'):
        for path in sorted((root / directory).glob('*.md')):
            rel = path.relative_to(root).as_posix()
            try:
                if rel not in records:
                    records[rel] = load(root, rel)
                    require(records[rel]['status'], f'missing epic Status: {rel}')
            except (OSError, ValueError, RecursionError) as exc:
                errors.append({'reason': str(exc), 'paths': [rel]})
    active = [r for r in records.values() if r['status'] in ('active', 'blocked')]
    candidates = active or [r for r in records.values() if r['kind'] == 'epic' and r['status'] == 'complete'
                            and review_passed(r['text'])]
    if len(candidates) > 1:
        errors.append({'reason': 'ambiguous work-unit selection', 'paths': sorted(r['path'] for r in candidates)})
    if errors:
        return None, 'discovery', errors
    record = candidates[0] if candidates else None
    source = 'none' if not record else 'roadmap-selected' if record['path'] == pointer else 'active-fallback' if active else 'reviewed-complete-fallback'
    return record, source, []
