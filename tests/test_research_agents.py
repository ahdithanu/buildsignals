import asyncio
import json
import subprocess
import sys

import pytest

from agent_runtime.research import run_research, validate_bundle, validate_findings


def bundle():
    return {'schema_version': 'research-context-v1',
            'evidence_kind': 'saved_workspace_facts_not_independently_verified',
            'evidence': [{'id': 'deal:1', 'text': '{"city": "Austin", "units": null}'}]}


def test_valid_bundle_and_exact_quotes():
    context = validate_bundle(bundle())
    output = {'facts': [{'source_id': 'deal:1', 'quote': '"city": "Austin"'}],
              'unknowns': ['Occupancy is unknown'], 'questions': ['Request rent roll']}
    assert validate_findings(json.dumps(output), context) == output


@pytest.mark.parametrize('edit', [
    lambda b: b.update(schema_version='other'),
    lambda b: b.update(evidence_kind='verified'),
    lambda b: b.update(evidence=[]),
    lambda b: b['evidence'].append(b['evidence'][0]),
    lambda b: b['evidence'][0].update(text='x' * 10001),
    lambda b: b['evidence'][0].update(text=float('nan')),
    lambda b: b['evidence'][0].update(secret='not allowed'),
])
def test_rejects_bad_context(edit):
    value = bundle()
    edit(value)
    with pytest.raises(ValueError):
        validate_bundle(value)


@pytest.mark.parametrize('payload', [
    {'facts': [{'source_id': 'foreign', 'quote': 'Austin'}], 'unknowns': [], 'questions': []},
    {'facts': [{'source_id': 'deal:1', 'quote': 'Guaranteed 20% return'}], 'unknowns': [], 'questions': []},
    {'facts': [{'source_id': 'deal:1', 'quote': ''}], 'unknowns': [], 'questions': []},
    {'facts': [], 'unknowns': [], 'questions': [], 'recommendation': 'Buy'},
    {'facts': [], 'unknowns': ['x'] * 21, 'questions': []},
])
def test_rejects_unsupported_output(payload):
    with pytest.raises(ValueError):
        validate_findings(json.dumps(payload), validate_bundle(bundle()))


@pytest.mark.parametrize(('execute', 'enabled'), [(False, '1'), (True, '0'), (False, '0')])
def test_execution_requires_both_gates_without_importing_sdk(monkeypatch, execute, enabled):
    monkeypatch.setenv('AGENT_RESEARCH_ENABLED', enabled)
    monkeypatch.setitem(sys.modules, 'agents', None)
    with pytest.raises(ValueError, match='research_execution_disabled'):
        asyncio.run(run_research(bundle(), execute=execute))


def test_dry_run_cli_needs_no_sdk_or_key(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    response = subprocess.run([sys.executable, '-m', 'agent_runtime.research'],
                              input=json.dumps(bundle()), text=True, capture_output=True,
                              timeout=5, check=True)
    assert json.loads(response.stdout)['model_calls'] == 0
    assert response.stderr == ''


def test_cli_errors_do_not_echo_input(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    response = subprocess.run([sys.executable, '-m', 'agent_runtime.research', '--execute'],
                              input='SECRET_PRIVATE_INPUT', text=True, capture_output=True,
                              timeout=5)
    assert response.returncode == 1 and not response.stdout
    assert 'SECRET_PRIVATE_INPUT' not in response.stderr
