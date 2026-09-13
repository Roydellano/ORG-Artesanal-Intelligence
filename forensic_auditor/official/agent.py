"""Optional masked AI tool scheduling; only the local evidence gate can publish."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from openrouter_client import chat, settings, OpenRouterError
from .audit import investigate

MAX_STEPS = 384
TOOLS = ('inspect_evidence', 'test_alternative', 'conclude')
PROMPT = 'official-controller-v1'


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lead: str = Field(pattern=r'^L-[a-f0-9]{32}$')
    tool: Literal['inspect_evidence', 'test_alternative', 'conclude']


def run(estate, seed, company, *, seconds=90, cancelled=None, usd_mxn_rate=None, fx_source='', model_chat=chat,
        request_delay=None, max_retries=3, zdr=None):
    started = time.perf_counter()
    config = settings()
    use_zdr = config.get('zdr', True) if zdr is None else bool(zdr)
    if use_zdr and config['model'].endswith(':free'):
        raise ValueError('Uploaded official estates require offline review or a non-free model with no-collection/ZDR routing')
    try:
        rate_val = usd_mxn_rate if usd_mxn_rate else ('20' if (not use_zdr or config['model'].endswith(':free')) else '')
        rate = Decimal(str(rate_val))
        source_val = fx_source.strip() if fx_source else ('Testing / free model' if (not use_zdr or config['model'].endswith(':free')) else '')
        if not rate.is_finite() or not 0 < rate < 1000 or not source_val:
            raise ValueError()
        fx_source = source_val
    except (InvalidOperation, ValueError):
        raise ValueError('AI mode requires a positive supplied USD/MXN exchange rate and its source') from None

    if request_delay is not None:
        delay = float(request_delay)
    else:
        env_delay = config.get('OPENROUTER_REQUEST_DELAY') if isinstance(config, dict) else None
        if env_delay is not None:
            delay = float(env_delay)
        elif model_chat is chat:
            delay = 5.0
        else:
            delay = 0.0

    def wait_delay(seconds_to_wait):
        if seconds_to_wait <= 0:
            return
        if cancelled is not None:
            if cancelled.wait(seconds_to_wait):
                raise ValueError('Investigation cancelled')
        else:
            time.sleep(seconds_to_wait)

    draft = investigate(estate, seed, company, seconds=seconds, cancelled=cancelled)
    case = deepcopy(draft)
    calls, steps, usd = 0, 0, Decimal(0)
    cost_known = True
    log = draft['investigation_log']
    aliases = {entry['lead_id']: 'L-' + uuid4().hex for entry in log}
    reverse = {value: key for key, value in aliases.items()}
    progress = {key: 0 for key in aliases}
    by_id = {entry['lead_id']: entry for entry in log}
    valid_ids = {finding['lead_id'] for finding in draft['findings']}
    events = []
    error = ''
    session_alias = 'S-' + uuid4().hex
    captured = []
    def usage(value):
        nonlocal usd, cost_known
        try:
            amount = Decimal(str(value.get('cost')))
            if not amount.is_finite() or amount < 0:
                raise ValueError()
            usd += amount
        except (InvalidOperation, ValueError):
            cost_known = False
    try:
        while any(stage < 3 for stage in progress.values()):
            remaining = seconds - (time.perf_counter() - started)
            if remaining < 5 or steps >= MAX_STEPS or (cancelled and cancelled.is_set()):
                raise ValueError('Investigation cancelled or action/time budget exhausted')
            # No raw identifiers, question text, descriptions, document text or policy prose crosses this boundary.
            context = {'session': session_alias, 'leads': [
                {'lead': aliases[lid], 'available_tool': TOOLS[stage], 'evidence_count': len(by_id[lid]['evidence']),
                 'predicate_supported': lid in valid_ids if stage > 0 else None}
                for lid, stage in progress.items() if stage < 3]}

            actions = None
            for attempt in range(max_retries + 1):
                if calls > 0 and delay > 0:
                    wait_delay(delay)
                remaining = seconds - (time.perf_counter() - started)
                if remaining < 5 or (cancelled and cancelled.is_set()):
                    raise ValueError('Investigation cancelled or action/time budget exhausted')
                calls += 1
                captured = []
                def capture(value):
                    captured.append(value)
                    usage(value)
                try:
                    chat_kwargs = {'max_tokens': config['max_tokens'], 'timeout': min(config['timeout'], remaining),
                                   'synthetic': False, 'usage_callback': capture}
                    if model_chat is chat:
                        chat_kwargs['zdr'] = use_zdr
                    response = model_chat([
                        {'role': 'system', 'content': 'Choose the next evidence-review actions. Return JSON {"actions":[{"lead":"supplied alias","tool":"available_tool"}]}, one to six distinct leads. Use only available tools. Inspect evidence, test alternatives, then conclude. Do not supply claims or prose.'},
                        {'role': 'user', 'content': json.dumps(context)}],
                        **chat_kwargs)
                    if not captured:
                        cost_known = False
                    response = response.strip()
                    if response.startswith('```json\n') and response.endswith('\n```'):
                        response = response[8:-4]
                    raw = json.loads(response)
                    if not isinstance(raw, dict) or set(raw) != {'actions'} or not isinstance(raw['actions'], list) or not 1 <= len(raw['actions']) <= 6:
                        raise ValueError('Malformed action batch')
                    parsed_actions = [Action.model_validate(action) for action in raw['actions']]
                    if len({a.lead for a in parsed_actions}) != len(parsed_actions):
                        raise ValueError('Repeated lead in action batch')
                    for action in parsed_actions:
                        lid = reverse.get(action.lead)
                        if lid not in progress or progress[lid] >= 3 or action.tool != TOOLS[progress[lid]]:
                            raise ValueError('Unknown, repeated or out-of-order action')
                    actions = parsed_actions
                    break
                except (OpenRouterError, ValueError, TypeError, KeyError) as e:
                    if (cancelled and cancelled.is_set()) or attempt >= max_retries:
                        raise
                    retry_wait = getattr(e, 'retry_after', None)
                    if retry_wait is not None and retry_wait > delay:
                        wait_delay(retry_wait - delay)
                    continue

            if not actions:
                raise ValueError('No actions returned')

            for action in actions:
                if cancelled and cancelled.is_set():
                    raise ValueError('Investigation cancelled')
                lid = reverse[action.lead]
                progress[lid] += 1
                steps += 1
                events.append({'step': steps, 'lead_id': lid, 'tool': action.tool,
                               'evidence': by_id[lid]['evidence'], 'rule_version': draft['rule_version'],
                               'result': by_id[lid]['alternative_review'] if action.tool == 'test_alternative' else
                                         ('Predicate validated locally' if lid in valid_ids else 'No accusation supported')})
    except (OpenRouterError, ValueError, TypeError, KeyError):
        if calls and not captured:
            cost_known = False
        error = 'AI review incomplete: provider failure, invalid action, cancellation or budget exhaustion. No unreviewed finding was published.'
    completed = {lid for lid, stage in progress.items() if stage == 3}
    case['findings'] = [f for f in draft['findings'] if f['lead_id'] in completed]
    case['leads_not_pursued'] = [l for l in draft['leads_not_pursued'] if l['lead_id'] in completed]
    for entry in log:
        if entry['lead_id'] not in completed:
            case['leads_not_pursued'].append({'lead_id': entry['lead_id'], 'entity': next((l['entity'] for l in draft['leads_not_pursued'] if l['lead_id'] == entry['lead_id']),
                                                                                      next((f['entities'][0] for f in draft['findings'] if f['lead_id'] == entry['lead_id']), 'RFC:' + company)),
                                             'signal': entry['hypothesis'], 'reason': 'Deferred: AI did not complete the required review. ' + error,
                                             'tool_calls_made': list(TOOLS[:progress[entry['lead_id']]]), 'closed_by': 'validator',
                                             'evidence_examined': entry['evidence'], 'state': 'deferred'})
    case['ai_events'] = events
    case['status'] = 'complete' if not error and cost_known and draft['status'] == 'offline_complete' else 'incomplete'
    case['completion_reason'] = error or ('Provider cost missing; judge export requires measured cost.' if not cost_known else 'All supplied leads reviewed.')
    case['run_metadata'] = {'llm_calls': calls, 'mxn_cost': float(usd*rate) if cost_known else None,
                            'wall_clock_seconds': round(time.perf_counter()-started, 6), 'deterministic': False,
                            'determinism_scope': 'Live model scheduling is not deterministic; completed-run replay preserves decisions and telemetry.',
                            'mode': 'ai', 'cost_by_role': {'controller_usd': str(usd)}, 'usd_mxn_rate': str(rate),
                            'fx_source': fx_source, 'model': config['model'], 'prompt_version': PROMPT,
                            'zdr': use_zdr}
    return case
