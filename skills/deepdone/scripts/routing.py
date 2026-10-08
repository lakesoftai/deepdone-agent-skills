#!/usr/bin/env python3
"""Read-only observations and pure, bounded DeepDone routing decisions."""
import re

import work_unit as w
import verification as v
import capture_reviewed_change_set as snapshot
import check_reviewed_change_set as terminal
import commit_progress as commit

MODES = {'inspect-only', 'one-step', 'until-milestone', 'until-review', 'until-epic',
         'until-commit-candidate', 'until-commit', 'end-to-end'}
PHASES = {'plan', 'sync', 'advance', 'decide', 'implement', 'verify', 'review', 'fixup', 'commit', 'pr', 'archive'}
ACTIONS = PHASES | {'candidate', 'pr-draft', 'pr-create', 'ci', 'verification-repair'}
PROTECTED = {'commit', 'pr-create', 'archive', 'push', 'merge', 'deploy'}


def milestones(text):
    """Parse automation's supported subset; legacy display stays permissive."""
    rows = []
    for line in w.section(text, 'Milestones').splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'- \[([ xX!\-])\] (\S.*?)\s*', line)
        if match:
            rows.append({'title': match[2], 'marker': match[1].lower(), 'depends': [], 'acceptance': ''})
        elif line.startswith('  ') and rows:
            field = re.fullmatch(r'\s+- (acceptance|depends on):\s*(.+)', line)
            if field:
                if field[1] == 'acceptance':
                    rows[-1]['acceptance'] = field[2]
                else:
                    rows[-1]['depends'] = [] if field[2] == 'none' else [s.strip() for s in field[2].split(',')]
        else:
            raise ValueError('unsupported milestone structure')
    names = [r['title'] for r in rows]
    w.require(rows and len(set(names)) == len(names) and all(r['acceptance'] for r in rows), 'missing/duplicate milestone title or acceptance')
    w.require(sum(r['marker'] == '-' for r in rows) <= 1, 'multiple active milestones')
    by_name = {r['title']: r for r in rows}
    def visit(name, chain):
        w.require(name in by_name and name not in chain, 'unresolved/cyclic milestone dependency')
        for dep in by_name[name]['depends']:
            visit(dep, chain | {name})
    for row in rows:
        visit(row['title'], set())
        if row['marker'] in {'-', 'x'}:
            w.require(all(by_name[d]['marker'] == 'x' for d in row['depends']), 'milestone contradicts dependency status')
    return rows


def next_slice(rows):
    done = {r['title'] for r in rows if r['marker'] == 'x'}
    active = next((r for r in rows if r['marker'] == '-'), None)
    for row in rows:
        if row['marker'] == '!':
            return row
        if row is active or (not active and row['marker'] == ' ' and set(row['depends']) <= done):
            return row
    return None


def context(value):
    w.require(type(value) is dict, 'context must be an object')
    w.require(not set(value) - {'requirements', 'scope', 'resolution', 'decision', 'findings', 'outcomes', 'target'}, 'unknown context field')
    if 'requirements' in value:
        w.require(v.nonempty(value['requirements']), 'requirements must be nonempty text')
    if 'scope' in value:
        w.scope(value['scope'])
    if 'target' in value:
        w.require(v.nonempty(value['target']), 'target must identify a slice')
    specs = {'resolution': ('stage', {'ready-to-start', 'implementation-in-progress', 'implementation-ready'}),
             'decision': ('need', {'analysis', 'user', 'future', 'none'}),
             'findings': ('disposition', {'local', 'decision', 'unaccepted'})}
    for key, (field, values) in specs.items():
        if key in value:
            item = value[key]
            v.shape(item, f'token slice basis {field}', key)
            w.require(all(v.nonempty(item[k]) for k in item), f'invalid {key} fields')
            w.require(item[field] in values, f'invalid {key} {field}')
    outcomes = value.get('outcomes', [])
    w.require(type(outcomes) is list, 'outcomes must be an array')
    for event in outcomes:
        v.shape(event, 'unit slice token phase action result reason', 'outcome')
        w.require(all(v.nonempty(x) for x in event.values()), 'invalid outcome fields')
        w.require(event['phase'] in PHASES and event['action'] in ACTIONS, 'invalid outcome phase/action')
        w.require(event['result'] in {'pass', 'fail', 'blocked', 'changed', 'unchanged'}, 'invalid outcome result')
        w.require(phase_for(event['action']) == event['phase'], 'outcome action/phase mismatch')
    return value


def phase_for(action):
    return {'candidate': 'commit', 'pr-draft': 'pr', 'pr-create': 'pr', 'ci': 'sync',
            'verification-repair': 'fixup'}.get(action, action)


def source_observation(root, record, scope):
    normalized = w.scope(scope)
    include, exclude = normalized['include'], normalized['exclude']
    absent = [p for p in include if not (root / p).exists()]
    present = [p for p in include if p not in absent]
    check = {'inputs': [{'path': p, 'role': 'source'} for p in present],
             'exclusions': [{'path': p} for p in exclude]}
    entries = v.fingerprint(root, record['path'], check, record['roadmap'], allow_empty=True)['entries'] if present else []
    files = {e['path']: e for e in entries if e['kind'] == 'file'}
    tracked = snapshot.run(['git', 'ls-tree', '-r', '-z', 'HEAD'], root, binary=True)
    w.require(tracked.returncode == 0, 'cannot observe HEAD source')
    head = {}
    for row in tracked.stdout.split(b'\0'):
        if row:
            meta, path = row.split(b'\t', 1)
            mode, kind, oid = meta.decode().split()
            path = path.decode('utf-8', 'surrogateescape')
            if any(v.within(path, p) for p in include) and not any(v.within(path, p) for p in exclude) and not v.evidence_path(path, record['path'], record['roadmap']):
                head[path] = (mode, oid)
    current = {}
    for path, item in files.items():
        data = (root / path).read_bytes()
        hashed = snapshot.run(['git', 'hash-object', '--stdin'], root, binary=True, input_data=data)
        w.require(hashed.returncode == 0, 'cannot hash observed source')
        oid = hashed.stdout.decode().strip()
        current[path] = (item['mode'], oid)
    owned = {p for p in head.keys() | current.keys() if head.get(p) != current.get(p)}
    w.validate_ownership(record['path'], owned)
    if present:
        v.ownership(root, record['path'], record['roadmap'], check, {'entries': entries}, owned)
    return {'entries': entries, 'absent': absent}, owned


def observe(root, *, task=None, ledger=None, ctx=None):
    """Use production validators. Context contains judgments, never gate overrides."""
    ctx = context({} if ctx is None else ctx)
    record, selection, errors = w.select(root, task=task, ledger=ledger)
    facts = {'unit': w.public(record), 'selection': selection, 'errors': errors,
             'stop': (root / '.deepdone/STOP').exists(), 'roadmap': record['roadmap'] if record else None, 'token': None,
             'readiness': 'absent', 'review': 'pending', 'review_valid': False,
             'integrated': False, 'commit_errors': [], 'milestones': [], 'slice': None,
             'final': False, 'changed': False, 'initial': False}
    if not record or errors:
        return facts
    try:
        text, path = record['text'], record['path']
        history = snapshot.review_entries(text)
        entry = history[-1] if history else {}
        facts['review'] = entry.get('result', 'pending')
        w.require(facts['review'] in {'pass', 'fail', 'pending', 'blocked'}, 'invalid Review result')
        w.require(record['status'] in {'active', 'blocked', 'complete'}, 'unknown work-unit status')
        if facts['review'] == 'pass' and record['status'] == 'complete':
            try:
                dirty, _ = terminal.check(root, path)
                facts['integrated'] = not dirty
            except (OSError, ValueError):
                pass
        try:
            facts['milestones'] = milestones(text) if record['kind'] == 'epic' else []
        except ValueError:
            if not facts['integrated']:
                raise  # Historical terminal validation stays usable without migration.
        if facts['integrated'] and record['kind'] == 'epic' and not facts['milestones']:
            facts.update(final=True, review_valid=True, slice=record['id'], token=v.sha(v.canonical({'unit': path, 'text': text})))
            return facts
        rows = facts['milestones']
        selected = next_slice(rows) if rows else None
        facts['slice'] = selected['title'] if selected else (record['id'] if record['kind'] == 'task' else rows[-1]['title'])
        facts['final'] = record['status'] == 'complete' and (record['kind'] == 'task' or all(r['marker'] == 'x' for r in rows))
        assessment = v.assess(root, path)
        facts['readiness'], facts['readiness_errors'] = assessment['state'], assessment['errors']
        contract = v.read_contract(text, path) if v.contract_span(text) else None
        inventory = v.inventory(root, path, contract)[0] if contract else None
        if record['kind'] == 'task':
            w.require('scope' not in ctx, 'task scope comes from its record')
            scopes = [record['task']['scope']]
        elif 'scope' in ctx:
            scopes = [ctx['scope']]
        elif inventory:
            # Exclusions belong to a check, not the union of all source inputs.
            scopes = [{'include': [i['path'] for i in c['inputs'] if i['role'] == 'source'],
                       'exclude': [e['path'] for e in c['exclusions']]}
                      for c in inventory['checks'] if any(i['role'] == 'source' for i in c['inputs'])]
        else:
            scopes = [entry.get('scope')]
        if not scopes or any(not scope or not scope.get('include') for scope in scopes):
            facts['errors'].append('ownership_unknown: declare inspected epic source scope')
            return facts
        projection, owned = [], set()
        for scope in scopes:
            observed, changed = source_observation(root, record, scope)
            projection.append(observed)
            owned.update(changed)
        facts['changed'] = bool(owned)
        if inventory:
            assessment = v.assess(root, path, owned=owned)
            facts['readiness'], facts['readiness_errors'] = assessment['state'], assessment['errors']
        relevant = record['task'] if record['kind'] == 'task' else {key: w.section(text, key) for key in ('Summary', 'Constraints', 'Milestones', 'Decisions')}
        facts['token'] = v.sha(v.canonical({'unit': {'path': path, 'identity': record['identity']}, 'contract': relevant, 'scope': scopes,
                                          'definitions': inventory['checks'] if inventory else None, 'source': projection}))
        # Status, receipt references and Review bookkeeping are intentionally not semantic progress.
        facts['initial'] = (not owned and not (contract and contract['attempts']) and
                            len(history) == 1 and entry.get('reviewed-at') == 'not-run' and facts['review'] == 'pending')
        if facts['review'] == 'pass':
            try:
                dirty, _ = terminal.check(root, path)
                facts['integrated'] = not dirty
            except (OSError, ValueError):
                pass
            if facts['integrated']:
                facts['review_valid'] = True
            else:
                validation = commit.validate_reviewed_change_set(root, path, text, None, commit.parse_status_z(root), check_staging=False)
                facts['review_valid'] = not validation[2]
                facts['review_errors'] = validation[2]
                facts['review_stale'] = bool(validation[3]) or assessment['state'] == 'stale'
                facts['commit_errors'] = (['staged_unowned'] if validation[4] else []) + commit.commit_gate_errors(
                    path, record['status'], text, commit.latest_verification_lines(text),
                    commit.review_lines(text), w.section(text, 'Open Loops').splitlines(), root=root)
        facts['review_slice'] = (next((row['title'] for row in reversed(rows) if row['marker'] == 'x'), None) if rows else record['id'])
        facts['blocked_slice'] = bool(selected and selected['marker'] == '!')
    except (OSError, ValueError, TypeError, KeyError) as exc:
        facts['errors'].append(str(exc))
    return facts


def resolve(facts, ctx):
    """Validate current semantic declarations; keep historical outcomes for budgets."""
    ctx = context(ctx)
    unit = facts['unit']
    events = ctx.get('outcomes', [])
    allowed = {r['title'] for r in facts['milestones']} or {facts['slice']}
    for event in events:
        w.require(unit and event['unit'] == unit['identity'] and event['slice'] in allowed, 'outcome belongs to another work unit/slice')
    for name in ('resolution', 'decision', 'findings'):
        if name in ctx:
            item = ctx[name]
            w.require(item['token'] == facts['token'] and item['slice'] in allowed, f'stale/inapplicable {name}')
    if 'target' in ctx:
        w.require(ctx['target'] in allowed, 'unknown target slice')
    return ctx


def classify(facts, ctx):
    """Pure dependency precedence. No action authority is created here."""
    def result(state, action, reason, slice_=None):
        return {'state': state, 'required_phase': phase_for(action), 'required_action': action,
                'reason': reason, 'slice': slice_ or facts['slice']}
    if facts['stop']:
        return result('blocked_needs_user', None, 'stop_file')
    if facts['errors']:
        return result('blocked_needs_user', None, 'invalid_observation')
    if not facts['unit']:
        return result('needs_intake' if ctx.get('requirements') else 'blocked_needs_user', 'plan' if ctx.get('requirements') else None, 'requirements' if ctx.get('requirements') else 'requirements_missing')
    if facts['integrated'] and facts['final']:
        return result('complete', None, 'integrated')
    if facts['readiness'] in {'invalid', 'pending'}:
        return result('blocked_needs_user', None, 'evidence_' + facts['readiness'])
    events = ctx.get('outcomes', [])
    last_work = next((e for e in reversed(events) if e['phase'] in {'implement', 'fixup'} and e['result'] == 'changed'), None)
    resolution = ctx.get('resolution', {})
    slice_ = last_work['slice'] if last_work else resolution.get('slice', facts['slice'])
    verified = next((e for e in reversed(events) if e['phase'] == 'verify' and e['result'] == 'pass' and e['token'] == facts['token'] and e['slice'] == slice_), None)
    reviewed = facts['review_valid']
    owes = bool(last_work and (not verified or events.index(verified) < events.index(last_work)))
    if facts['readiness'] == 'failed':
        if ctx.get('findings', {}).get('disposition') == 'local':
            return result('needs_verification', 'verification-repair', 'verification_failed', slice_)
        return result('needs_tech_decision', 'decide', 'verification_failure_analysis', slice_)
    if owes or (resolution.get('stage') == 'implementation-ready' and not verified and not reviewed):
        return result('needs_verification', 'verify', 'verify_boundary', slice_)
    if facts['readiness'] == 'stale':
        return result('needs_verification', 'verify', 'stale_readiness', slice_)
    if facts['readiness'] == 'pass' and not reviewed:
        if facts['review'] == 'fail':
            finding = ctx.get('findings', {})
            if finding.get('disposition') == 'local':
                return result('needs_review_fix', 'fixup', 'accepted_local_findings', finding['slice'])
            return result('needs_tech_decision', 'decide', 'review_findings', slice_)
        if facts['review'] == 'pass' and not facts.get('review_stale'):
            return result('blocked_needs_user', None, 'invalid_review', slice_)
        if not verified:
            return result('needs_resume', 'sync', 'verify_outcome_unknown', slice_)
        return result('needs_review', 'review', 'review_due', verified['slice'])
    if reviewed and facts['final']:
        return result('ready_to_commit', 'candidate', 'final_review_pass')
    decision = ctx.get('decision', {}).get('need')
    if decision == 'user':
        return result('blocked_needs_user', None, 'user_input_required')
    if decision == 'analysis':
        return result('needs_tech_decision', 'decide', 'analysis_required')
    if facts.get('blocked_slice'):
        return result('blocked_needs_user', None, 'milestone_blocked')
    if reviewed and not facts['final'] and facts['unit']['status'] == 'complete':
        return result('needs_resume', 'sync', 'premature_completion')
    if reviewed and facts['milestones'] and all(row['marker'] == 'x' for row in facts['milestones']):
        return result('needs_review', 'review', 'final_completion_due')
    if facts['unit']['status'] == 'blocked':
        return result('needs_resume', 'sync', 'blocked_record')
    if reviewed or facts['initial'] or resolution.get('stage') in {'ready-to-start', 'implementation-in-progress'}:
        return result('ready_to_implement', 'implement', 'implementation_ready', resolution.get('slice'))
    return result('needs_resume', 'sync', 'progress_unknown')


def admit(facts, decision, ctx, *, mode='one-step', requested=None, authority=None):
    w.require(mode in MODES, 'unknown mode')
    w.require(requested is None or requested in ACTIONS, 'unknown requested action')
    authority = {} if authority is None else authority
    w.require(type(authority) is dict and not set(authority) - PROTECTED and all(type(x) is bool for x in authority.values()), 'invalid authority')
    events = ctx.get('outcomes', [])
    action = decision['required_action']
    stop = None
    target = ctx.get('target') or (events[0]['slice'] if events else decision['slice'])
    current = [e for e in events if e['token'] == facts['token']]
    review_events = [e for e in events if e['phase'] == 'review']
    verified_target = any(e['phase'] == 'verify' and e['result'] == 'pass' and e['slice'] == target for e in current)
    if facts['review_valid'] and target == facts.get('review_slice', decision['slice']):
        verified_target = True
    if mode == 'inspect-only':
        stop = 'inspect_only'
    elif mode == 'one-step' and events:
        stop = 'phase_budget'
    elif mode == 'until-review' and review_events:
        stop = 'review_outcome'
    elif mode == 'until-milestone' and verified_target:
        stop = 'milestone_verified'
    elif mode in {'until-epic', 'until-review'} and facts['review_valid'] and (mode == 'until-review' or facts['final']):
        stop = 'review_target_reached'
    elif mode == 'until-commit-candidate' and any(e['action'] == 'candidate' and e['result'] == 'pass' for e in current):
        stop = 'candidate_prepared'
    elif mode in {'until-commit', 'end-to-end'} and any(e['action'] == 'commit' for e in events):
        stop = 'commit_outcome'
    elif decision['state'] == 'blocked_needs_user':
        stop = decision['reason']
    if not stop and action == 'candidate' and ((requested == 'commit' and mode == 'one-step') or mode in {'until-commit', 'end-to-end'}):
        action = 'commit'
    if not stop and decision['state'] == 'complete':
        if requested in {'pr', 'pr-draft', 'pr-create', 'ci'}:
            action = 'pr-draft' if requested == 'pr' else requested
        elif requested in {'advance', 'archive'} and facts['unit']['kind'] == 'epic':
            if requested == 'advance' and not facts.get('roadmap'):
                stop = 'no_associated_roadmap'
            action = requested
        else:
            stop = 'complete' if not requested else 'unsupported_task_lifecycle'
    if not stop and requested and requested not in {action, phase_for(action)}:
        if mode == 'one-step' or requested in {'advance', 'archive', 'pr', 'pr-draft', 'pr-create', 'ci'}:
            stop = 'requested_phase_mismatch'
    if not stop and action in PROTECTED:
        granted = authority.get(action, action == 'commit' and mode in {'until-commit', 'end-to-end'})
        if not granted:
            stop = 'authority_required'
        elif action == 'commit' and facts['commit_errors']:
            stop = 'commit_blocked'
    if not stop and action == 'verification-repair':
        if any(e['action'] == action for e in events):
            stop = 'verification_repair_budget'
    if not stop and action == 'fixup' and any(e['action'] == 'fixup' for e in events):
        stop = 'review_repair_budget'
    if not stop and events and events[-1]['phase'] == phase_for(action) and events[-1]['token'] == facts['token'] and events[-1]['reason'] == decision['reason']:
        stop = 'unchanged_repeat'
    return {**decision, 'admitted_phase': None if stop else phase_for(action),
            'admitted_action': None if stop else action, 'stop_reason': stop,
            'target': target, 'authority': authority}


def route(facts, ctx=None, **options):
    try:
        ctx = resolve(facts, {} if ctx is None else ctx)
        return {**admit(facts, classify(facts, ctx), ctx, **options),
                'unit': facts['unit'], 'observation_token': facts['token']}
    except (ValueError, TypeError, KeyError) as exc:
        return {'state': 'context_error', 'required_phase': None, 'required_action': None,
                'admitted_phase': None, 'admitted_action': None, 'stop_reason': 'invalid_context', 'errors': [str(exc)]}
