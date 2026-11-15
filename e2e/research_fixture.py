"""Synthetic worker output for browser acceptance only; never a model response."""
import json
from copy import deepcopy


def offline_research(bundle, **_settings):
    row = bundle['evidence'][0]
    name = json.loads(row['text'])['name']
    assert name.startswith('SYNTHETIC'), 'Research browser fixtures require synthetic deals'
    findings = {'facts': [{'source_id': row['id'], 'quote': name}],
                'unknowns': ['Occupancy has not been verified'],
                'questions': ['Request the current rent roll']}
    return {'schema_version': 'research-output-v1', 'model_generated': True, 'research_only': True,
            'evidence_kind': bundle['evidence_kind'],
            'context_authenticity': 'not_verified_by_local_runner',
            'stages': [{'stage': stage, 'findings': deepcopy(findings)}
                       for stage in ('Evidence analyst', 'Diligence reviewer')],
            'usage': [{'requested_model': 'synthetic/offline', 'served_model': 'synthetic/offline',
                       'provider': 'SYNTHETIC TEST ONLY', 'latency_ms': 0, 'prompt_tokens': None,
                       'completion_tokens': None, 'total_tokens': None, 'cost': None,
                       'response_id': None} for _ in range(2)],
            'limitations': ['Synthetic browser acceptance response; no model was called.']}
