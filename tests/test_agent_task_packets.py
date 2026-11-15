import builtins
import io
import json
from copy import deepcopy

import pytest

from scripts import agent_task_packets as planner


def document():
    return {'version': 1, 'tasks': [{
        'id': 'backend', 'agent': 'codex', 'reviewer': 'claude_code',
        'objective': 'Add focused offline tests.',
        'files': ['app/services/example.py', 'tests/test_example.py'],
    }]}


def test_plan_has_disjoint_writer_and_explicit_read_only_review_packets():
    source = document()
    before = deepcopy(source)
    result = planner.build_plan(source)
    assert source == before
    assert result['kind'] == 'coding_agent_task_plan'
    assert result['version'] == 1
    assert result['execution_authorized'] is False
    assert result['sandbox_enforced'] is False
    writer, reviewer = result['packets']
    assert writer['task_id'] == reviewer['task_id'] == 'backend'
    assert writer['agent'] == 'codex' and writer['role'] == 'writer'
    assert writer['owned_files'] == source['tasks'][0]['files']
    assert reviewer['agent'] == 'claude_code'
    assert reviewer['role'] == 'read_only_reviewer'
    assert reviewer['owned_files'] == []
    assert reviewer['review_files'] == writer['owned_files']
    assert 'PLAN ONLY' in writer['prompt']
    assert 'read-only' in reviewer['prompt']
    assert 'not a sandbox' in writer['prompt']
    assert 'symlinks' in ' '.join(result['limitations'])
    writer['owned_files'].append('other.py')
    assert source == before
    assert reviewer['review_files'] == source['tasks'][0]['files']


@pytest.mark.parametrize('agent,reviewer,adapter', [
    ('codex', 'claude_code', 'AGENTS.md'),
    ('claude_code', 'antigravity', 'CLAUDE.md'),
    ('antigravity', 'codex', 'GEMINI.md'),
])
def test_each_portable_agent_gets_harness_prompt(agent, reviewer, adapter):
    source = document()
    source['tasks'][0].update(agent=agent, reviewer=reviewer)
    writer, review = planner.build_plan(source)['packets']
    assert adapter in writer['prompt']
    assert 'docs/agent-handoff.md' in writer['prompt']
    assert 'docs/agent-onboarding.md' in review['prompt']
    assert 'no edits' in review['prompt']
    assert 'No commits' in writer['prompt']
    assert 'production' in writer['prompt']


@pytest.mark.parametrize('path', [
    '', '.', '..', '/tmp/code.py', '//server/code.py', '../outside.py',
    'app/../code.py', './app/code.py', 'app//code.py', 'app/code.py/',
    'C:/code.py', r'C:\code.py', r'app\code.py', '~/code.py',
    'app/*.py', 'app/?.py', 'app/[ab].py', 'app/{a,b}.py',
    'app/file name.py', 'app/code.py\n', 'app/\x00file.py',
    'app/%2e%2e/code.py', 'app/caf\u00e9.py', 'app/code.py:stream',
    '.git/config', 'app/.GIT/config', '.worktrees/other/app.py',
    '.env', '.env.local', 'app/.env.example', 'data/capture.json',
    'DATA/capture.json', 'docs/internal/receipt.md', 'docs/INTERNAL/receipt.md',
    'private/receipt.json', 'docs/private/notes.md', 'receipts/result.json',
    'docs/private-receipt.md', 'docs/release_receipt.md',
    'app/NUL.py', 'app/com1.py', 'app/name.', 'app/-option.py',
])
def test_unsafe_or_protected_file_ownership_is_rejected(path):
    source = document()
    source['tasks'][0]['files'] = [path]
    with pytest.raises(ValueError, match='^Invalid task packet plan$'):
        planner.build_plan(source)


@pytest.mark.parametrize('path', ['Makefile', '.gitignore', '.github/workflows/tests.yml',
                                  'src/components/Widget.test.tsx', 'docs/public-notes.md'])
def test_portable_exact_file_names_are_allowed(path):
    source = document()
    source['tasks'][0]['files'] = [path]
    assert planner.build_plan(source)['packets'][0]['owned_files'] == [path]


@pytest.mark.parametrize('paths', [
    ['app/file.py', 'app/file.py'], ['app/File.py', 'app/file.py'],
    ['app', 'app/file.py'], ['app/file.py', 'app'],
])
@pytest.mark.parametrize('separate_tasks', [False, True])
def test_duplicate_casefolded_and_parent_child_ownership_conflicts(paths, separate_tasks):
    source = document()
    if separate_tasks:
        source['tasks'][0]['files'] = [paths[0]]
        source['tasks'].append(source['tasks'][0] | {'id': 'frontend', 'files': [paths[1]]})
    else:
        source['tasks'][0]['files'] = paths
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_sibling_paths_are_not_mistaken_for_overlap():
    source = document()
    source['tasks'][0]['files'] = ['app/file.py']
    source['tasks'].append(source['tasks'][0] | {'id': 'other', 'files': ['app/file.pyx']})
    assert len(planner.build_plan(source)['packets']) == 4


@pytest.mark.parametrize('field', ['version', 'tasks'])
def test_root_fields_required(field):
    source = document()
    del source[field]
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('field', ['id', 'agent', 'reviewer', 'objective', 'files'])
def test_task_fields_required(field):
    source = document()
    del source['tasks'][0][field]
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('field,value', [
    ('id', True), ('id', ''), ('id', '../id'), ('id', 'UPPER'),
    ('agent', 'shell'), ('agent', []), ('reviewer', None), ('reviewer', 'codex'),
    ('objective', ''), ('objective', '  '), ('objective', True),
    ('objective', 'text\x1b[31m'), ('objective', 'line\nbreak'),
    ('objective', '\ud800'), ('files', 'app/file.py'), ('files', []),
    ('files', [True]), ('files', {}),
])
def test_task_types_values_and_reviewer_independence(field, value):
    source = document()
    source['tasks'][0][field] = value
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('source', [None, [], 'text', True,
                                         {'version': True, 'tasks': []},
                                         {'version': 1.0, 'tasks': []},
                                         {'version': 2, 'tasks': []},
                                         {'version': 1, 'tasks': {}},
                                         {'version': 1, 'tasks': [None]}])
def test_root_types_and_versions_rejected(source):
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('nested', [False, True])
def test_unknown_fields_rejected_without_echo(nested):
    source = document()
    target = source['tasks'][0] if nested else source
    target['secret-value-must-not-echo'] = 'private secret'
    with pytest.raises(ValueError) as error:
        planner.build_plan(source)
    assert str(error.value) == 'Invalid task packet plan'


def test_duplicate_task_ids_rejected():
    source = document()
    source['tasks'].append(source['tasks'][0] | {'files': ['tests/other.py']})
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('field,limit', [('id', 'MAX_ID_LENGTH'),
                                     ('objective', 'MAX_OBJECTIVE_BYTES')])
def test_text_size_boundaries(field, limit):
    source = document()
    source['tasks'][0][field] = 'a' * getattr(planner, limit)
    planner.build_plan(source)
    source['tasks'][0][field] += 'a'
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_unicode_objective_limit_is_bytes_not_characters():
    source = document()
    source['tasks'][0]['objective'] = '\u00e9' * planner.MAX_OBJECTIVE_BYTES
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_path_size_boundary():
    source = document()
    source['tasks'][0]['files'] = ['a' * planner.MAX_PATH_BYTES]
    planner.build_plan(source)
    source['tasks'][0]['files'][0] += 'a'
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_task_count_boundaries():
    source = document()
    source['tasks'] = [source['tasks'][0] | {'id': f'task-{index}', 'files': [f'app/f{index}.py']}
                       for index in range(planner.MAX_TASKS)]
    assert len(planner.build_plan(source)['packets']) == 2 * planner.MAX_TASKS
    source['tasks'].append(source['tasks'][0] | {'id': 'extra', 'files': ['extra.py']})
    with pytest.raises(ValueError):
        planner.build_plan(source)
    source['tasks'] = []
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_per_task_file_count_boundaries():
    source = document()
    source['tasks'][0]['files'] = [f'app/f{i}.py' for i in range(planner.MAX_FILES_PER_TASK)]
    planner.build_plan(source)
    source['tasks'][0]['files'].append('extra.py')
    with pytest.raises(ValueError):
        planner.build_plan(source)


def test_total_file_count_boundaries():
    source = document()
    source['tasks'] = [source['tasks'][0] | {
        'id': f'task-{i}', 'files': [f'app/t{i}f{j}.py' for j in range(planner.MAX_FILES_PER_TASK)]}
        for i in range(planner.MAX_TOTAL_FILES // planner.MAX_FILES_PER_TASK)]
    planner.build_plan(source)
    source['tasks'].append(source['tasks'][0] | {'id': 'extra', 'files': ['extra.py']})
    with pytest.raises(ValueError):
        planner.build_plan(source)


@pytest.mark.parametrize('raw', [
    '', '{', '[]', '{"version":1,"version":1,"tasks":[]}',
    '{"version":NaN,"tasks":[]}', '{"version":Infinity,"tasks":[]}',
    '{"version":1,"tasks":[]} trailing', b'\xff',
    '[' * 2000 + ']' * 2000,
])
def test_strict_json_and_malformed_input_errors_are_generic(raw):
    with pytest.raises(ValueError, match='^Invalid task packet plan$'):
        planner.plan_json(raw)


def test_duplicate_nested_json_fields_rejected():
    raw = json.dumps(document()).replace('"agent": "codex"', '"agent":"codex","agent":"codex"')
    with pytest.raises(ValueError):
        planner.plan_json(raw)


def test_raw_input_byte_limit_includes_whitespace():
    raw = json.dumps(document())
    padded = raw + ' ' * (planner.MAX_INPUT_BYTES - len(raw.encode()))
    planner.plan_json(padded)
    with pytest.raises(ValueError):
        planner.plan_json(padded + ' ')


def test_json_and_direct_plan_agree_and_are_deterministic():
    source = document()
    assert planner.plan_json(json.dumps(source)) == planner.build_plan(source)
    assert planner.plan_json(json.dumps(source).encode()) == planner.build_plan(source)
    assert planner.build_plan(source) == planner.build_plan(deepcopy(source))


def test_cli_only_reads_bounded_stdin_and_writes_json_stdout(monkeypatch):
    source = document()
    stdin = io.StringIO(json.dumps(source))
    stdout = io.StringIO()

    def forbidden(*_args, **_kwargs):
        pytest.fail('Planner must not access files, execute commands, or use the network')

    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr('os.system', forbidden)
    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('socket.socket', forbidden)
    assert planner.main([], stdin=stdin, stdout=stdout) == 0
    assert json.loads(stdout.getvalue()) == planner.build_plan(source)


@pytest.mark.parametrize('raw', ['{"private-password": "do-not-echo"}', 'NaN', '{'])
def test_cli_errors_are_json_redacted_and_nonzero(raw):
    stdout = io.StringIO()
    assert planner.main([], stdin=io.StringIO(raw), stdout=stdout) == 2
    assert json.loads(stdout.getvalue()) == {'error': 'Invalid task packet plan'}


def test_cli_rejects_arguments_and_never_accepts_output_file():
    class Unreadable:
        def read(self, _size):
            pytest.fail('Invalid CLI flags must fail before reading input')

    stdout = io.StringIO()
    assert planner.main(['--output', 'result.json'], stdin=Unreadable(), stdout=stdout) == 2
    assert json.loads(stdout.getvalue()) == {'error': 'Invalid task packet plan'}


def test_cli_read_is_bounded():
    class Input:
        def read(self, size):
            assert size == planner.MAX_INPUT_BYTES + 1
            return ' ' * size

    stdout = io.StringIO()
    assert planner.main([], stdin=Input(), stdout=stdout) == 2
