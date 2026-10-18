"""Tests for the PR event trigger: templates/pr-review-trigger.yml and
scripts/setup-host-runner.sh.

The workflow's job condition is evaluated with a small interpreter for the
subset of the Actions expression language the template uses, against event
payloads shaped like Gitea's (which may spell actions `synchronized` and
`label_updated` and may omit the label). Its step script runs under bash with
a fake pr-trigger. The setup script runs against a temporary HOME with fake
gitea-runner, systemctl and loginctl programs first on PATH, so nothing on
this machine is registered, enabled or written outside the temporary folder.
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / 'templates' / 'pr-review-trigger.yml'
SETUP = ROOT / 'scripts' / 'setup-host-runner.sh'
REPO = 'owner/project'
HEAD = 'a' * 40
MISSING = object()


# Actions expression subset: literals, property paths, !, ==, !=, &&, || and ().
TOKEN = re.compile(r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<op>==|!=|&&|\|\||!|\(|\))|(?P<name>[A-Za-z_][\w.]*))")


def tokenize(text):
    tokens, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise ValueError(f'unsupported expression syntax at: {text[pos:]!r}')
        tokens.append((match.lastgroup, match.group(match.lastgroup)))
        pos = match.end()
    return tokens


def truthy(value):
    return value not in (None, False, 0, '') and not (isinstance(value, float) and math.isnan(value))


def as_number(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        try:
            return float(value) if value.strip() else 0
        except ValueError:
            return math.nan
    return value


def loose_equal(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()
    if type(left) is type(right):
        return left == right
    return as_number(left) == as_number(right)


class Expression:
    def __init__(self, text, context):
        text = text.strip()
        if text.startswith('${{') and text.endswith('}}'):
            text = text[3:-2]
        self.tokens, self.pos, self.context = tokenize(text), 0, context

    def evaluate(self):
        value = self.either()
        if self.pos != len(self.tokens):
            raise ValueError(f'trailing tokens: {self.tokens[self.pos:]}')
        return value

    def peek(self):
        return self.tokens[self.pos][1] if self.pos < len(self.tokens) else None

    def take(self):
        self.pos += 1
        return self.tokens[self.pos - 1]

    def either(self):
        value = self.both()
        while self.peek() == '||':
            self.take()
            right = self.both()
            value = value if truthy(value) else right
        return value

    def both(self):
        value = self.compare()
        while self.peek() == '&&':
            self.take()
            right = self.compare()
            value = right if truthy(value) else value
        return value

    def compare(self):
        value = self.unary()
        while self.peek() in ('==', '!='):
            op = self.take()[1]
            right = self.unary()
            value = loose_equal(value, right) == (op == '==')
        return value

    def unary(self):
        if self.peek() == '!':
            self.take()
            return not truthy(self.unary())
        return self.primary()

    def primary(self):
        kind, text = self.take()
        if text == '(':
            value = self.either()
            if self.take()[1] != ')':
                raise ValueError('expected )')
            return value
        if kind == 'str':
            return text[1:-1].replace("''", "'")
        if kind == 'name':
            if text in ('true', 'false', 'null'):
                return {'true': True, 'false': False, 'null': None}[text]
            value = self.context
            for part in text.split('.'):
                value = value.get(part) if isinstance(value, dict) else None
            return value
        raise ValueError(f'unexpected token {text!r}')


def event(action, label=MISSING, draft=False, head_repo=REPO):
    payload = {'action': action,
               'pull_request': {'number': 7, 'draft': draft,
                                'head': {'sha': HEAD, 'repo': {'full_name': head_repo} if head_repo else None}}}
    if label is not MISSING:
        payload['label'] = None if label is None else {'name': label}
    return payload


def context(payload):
    return {'github': {'repository': REPO, 'event': payload}}


class WorkflowTemplate:
    """Pulls the job condition, step env and step script out of the template text."""

    def __init__(self, text):
        self.text = text
        self.lines = text.splitlines()

    def block_after(self, pattern):
        for index, line in enumerate(self.lines):
            if re.fullmatch(pattern, line):
                indent = len(line) - len(line.lstrip())
                body = []
                for following in self.lines[index + 1:]:
                    if following.strip() and len(following) - len(following.lstrip()) <= indent:
                        break
                    body.append(following)
                return body
        raise AssertionError(f'no line matching {pattern!r}')

    def condition(self):
        return ' '.join(line.strip() for line in self.block_after(r'\s+if: >-'))

    def step_env(self):
        env = {}
        for line in self.block_after(r'\s+env:'):
            match = re.fullmatch(r'\s+(\w+): \$\{\{ (.+) \}\}', line)
            if match:
                env[match.group(1)] = match.group(2)
        return env

    def script(self):
        body = self.block_after(r'\s+run: \|')
        indent = min(len(line) - len(line.lstrip()) for line in body if line.strip())
        return '\n'.join(line[indent:] for line in body) + '\n'


class WorkflowTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = WorkflowTemplate(WORKFLOW.read_text())

    def runs(self, payload):
        return truthy(Expression(self.template.condition(), context(payload)).evaluate())

    def test_first_line_is_the_version_comment(self):
        self.assertEqual(self.template.lines[0], '# pr-review-trigger template v1')

    def test_trigger_types_branch_runner_and_concurrency(self):
        text = self.template.text
        self.assertRegex(text, r'(?m)^on:\n  pull_request_target:\n    types: \[opened, synchronize, reopened, labeled\]\n'
                               r'    branches: \[develop\]$')
        self.assertRegex(text, r'(?m)^    runs-on: factory-host$')
        self.assertRegex(text, r'(?m)^  group: .*\$\{\{ github\.repository \}\}.*'
                               r'\$\{\{ github\.event\.pull_request\.number \}\}$')
        self.assertNotIn('nightcrew-host', text)

    def test_structure_when_pyyaml_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML not installed; the regex checks above still cover the structure')
        data = yaml.safe_load(self.template.text)
        trigger = data.get('on', data.get(True))
        self.assertEqual(list(trigger), ['pull_request_target'])
        self.assertEqual(trigger['pull_request_target'],
                         {'types': ['opened', 'synchronize', 'reopened', 'labeled'], 'branches': ['develop']})
        self.assertEqual(list(data['jobs']), ['queue'])
        job = data['jobs']['queue']
        self.assertEqual(job['runs-on'], 'factory-host')
        self.assertEqual(len(job['steps']), 1)
        self.assertEqual(set(job['steps'][0]), {'name', 'env', 'run'})
        self.assertFalse(data['concurrency']['cancel-in-progress'])

    def test_no_checkout_actions_secrets_or_machine_paths(self):
        text = self.template.text
        code = '\n'.join(line for line in self.template.lines if not line.lstrip().startswith('#'))
        for forbidden in ('uses:', 'secrets', 'checkout', 'actions/'):
            self.assertNotIn(forbidden, code)
        for forbidden in ('~', '/home/', '/Users/'):
            self.assertNotIn(forbidden, text)
        self.assertIsNone(re.search(r'\b\d{1,3}(\.\d{1,3}){3}\b', text), 'no IP addresses')
        self.assertIn('"$HOME/.local/bin/pr-trigger"', text)

    def test_condition_runs_for_pushes_opens_and_reopens_in_either_spelling(self):
        for action in ('opened', 'reopened', 'synchronize', 'synchronized'):
            with self.subTest(action=action):
                self.assertTrue(self.runs(event(action)))

    def test_condition_skips_drafts_and_forks(self):
        for action, label in (('opened', MISSING), ('synchronized', MISSING), ('labeled', 'review:requested'),
                              ('label_updated', None)):
            with self.subTest(action=action):
                self.assertFalse(self.runs(event(action, label, draft=True)))
                self.assertFalse(self.runs(event(action, label, head_repo='someone/project')))
                self.assertFalse(self.runs(event(action, label, head_repo=None)))

    def test_condition_for_label_events(self):
        cases = [('review:requested', True), ('review:findings', True), ('Review:Requested', True),
                 ('review:clean', False), ('review:clear', False), ('review:resolved', False), ('kind:bug', False),
                 ('', True), (None, True), (MISSING, True)]
        for action in ('labeled', 'label_updated'):
            for label, expected in cases:
                with self.subTest(action=action, label=label):
                    self.assertEqual(self.runs(event(action, label)), expected)

    def run_step(self, payload, exit_code=0):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            calls = home / 'calls.jsonl'
            fake = home / '.local' / 'bin' / 'pr-trigger'
            fake.parent.mkdir(parents=True)
            fake.write_text(f'#!{sys.executable}\nimport json, sys\n'
                            f'open({str(calls)!r}, "a").write(json.dumps(sys.argv[1:]) + "\\n")\n'
                            f'sys.exit({exit_code})\n')
            fake.chmod(0o755)
            env = {'HOME': str(home), 'PATH': '/usr/bin:/bin'}
            for name, expression in self.template.step_env().items():
                value = Expression(expression, context(payload)).evaluate()
                env[name] = '' if value is None else str(value)
            result = subprocess.run(['bash', '-e', '-c', self.template.script()], env=env,
                                    capture_output=True, text=True, timeout=30)
            lines = calls.read_text().splitlines() if calls.exists() else []
            return result, [json.loads(line) for line in lines]

    def test_step_passes_event_fields_and_label_only_when_named(self):
        base = ['--repo', REPO, '--pr', '7', '--sha', HEAD]
        cases = [(event('synchronized'), base + ['--event', 'synchronized']),
                 (event('labeled', 'review:requested'), base + ['--event', 'labeled', '--label', 'review:requested']),
                 (event('label_updated', None), base + ['--event', 'label_updated']),
                 (event('label_updated', ''), base + ['--event', 'label_updated'])]
        for payload, expected in cases:
            with self.subTest(action=payload['action'], label=payload.get('label')):
                result, calls = self.run_step(payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [expected])

    def test_step_keeps_unusual_values_as_single_arguments(self):
        payload = event('labeled', "review:requested; echo 'x' $(id)")
        result, calls = self.run_step(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0][-2:], ['--label', "review:requested; echo 'x' $(id)"])

    def test_step_fails_with_pr_trigger_exit_status(self):
        result, calls = self.run_step(event('opened'), exit_code=3)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(len(calls), 1)


FAKE_RUNNER = r'''
import json, os, re, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(json.dumps({'tool': 'gitea-runner', 'argv': args,
                          'env_token': os.environ.get('GITEA_RUNNER_REGISTRATION_TOKEN')}) + '\n')
if args == ['--version']:
    print('gitea-runner version v0-test')
    sys.exit(0)
if 'register' in args and '--help' in args:
    mode = os.environ.get('FAKE_RUNNER_HELP', 'token-file')
    print('Flags:')
    print('  --token string   Runner token' + (' (or set the GITEA_RUNNER_REGISTRATION_TOKEN envvar)' if mode != 'none' else ''))
    if mode == 'token-file':
        print('  --token-file string   Path to a file containing the runner token')
    sys.exit(0)
if 'register' in args:
    config = Path(args[args.index('--config') + 1]).read_text()
    runner_file = Path(re.search(r'file: "([^"]+)"', config).group(1))
    if '--token-file' in args:
        token = Path(args[args.index('--token-file') + 1]).read_text().strip()
    else:
        token = os.environ['GITEA_RUNNER_REGISTRATION_TOKEN']
    if os.environ.get('FAKE_RUNNER_ECHO'):
        print('registering with token ' + token)
    if os.environ.get('FAKE_RUNNER_FAIL'):
        sys.exit(1)
    runner_file.write_text('{"uuid": "fake"}')
    runner_file.chmod(0o644)
    sys.exit(0)
sys.exit(9)
'''

FAKE_SYSTEMCTL = r'''
import json, os, sys
args = sys.argv[1:]
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(json.dumps({'tool': 'systemctl', 'argv': args}) + '\n')
if 'is-enabled' in args:
    print(os.environ.get('FAKE_ENABLED', 'enabled'))
elif 'is-active' in args:
    print(os.environ.get('FAKE_ACTIVE', 'active'))
'''

FAKE_LOGINCTL = r'''
import os
print(os.environ.get('FAKE_LINGER', 'yes'))
'''

TOKEN_VALUE = 'sekrit-registration-token-42'


class SetupHostRunnerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.home = self.tmp / 'home'
        self.home.mkdir()
        self.bin = self.tmp / 'bin'
        self.log = self.tmp / 'calls.jsonl'
        for name, source in (('gitea-runner', FAKE_RUNNER), ('systemctl', FAKE_SYSTEMCTL), ('loginctl', FAKE_LOGINCTL)):
            self.write_program(self.bin / name, source)
        self.config = self.home / '.config' / 'factory-host-runner' / 'config.yaml'
        self.unit = self.home / '.config' / 'systemd' / 'user' / 'gitea-runner-factory-host.service'
        self.state = self.home / '.local' / 'state' / 'factory-host-runner'
        self.runner_file = self.state / '.runner'
        self.token = self.tmp / 'runner-token'
        self.token.write_text(TOKEN_VALUE + '\n')
        self.token.chmod(0o600)

    def write_program(self, path, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!{sys.executable}\n' + source)
        path.chmod(0o755)

    def setup(self, *args, **env):
        values = {'HOME': str(self.home), 'PATH': f'{self.bin}:/usr/bin:/bin', 'FAKE_LOG': str(self.log),
                  'LANG': 'C.UTF-8'}
        values.update(env)
        result = subprocess.run(['bash', str(SETUP), *args], env=values, capture_output=True, text=True, timeout=60)
        self.assertNotIn(TOKEN_VALUE, result.stdout + result.stderr)
        return result

    def calls(self, tool=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [row for row in rows if tool is None or row['tool'] == tool]

    def register_calls(self):
        return [row for row in self.calls('gitea-runner') if 'register' in row['argv'] and '--help' not in row['argv']]

    def register(self, *extra, **env):
        return self.setup('register', '--instance', 'https://gitea.example.test', '--token-file', str(self.token),
                          '--name', 'factory-host-test', *extra, **env)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_render_writes_private_config_and_unit_once(self):
        self.assert_ok(self.setup('render'))
        config = self.config.read_text()
        self.assertIn(f'file: "{self.state}/.runner"', config)
        self.assertIn(f'workdir_parent: "{self.state}/work"', config)
        self.assertIn('- "factory-host:host"', config)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        unit = self.unit.read_text()
        self.assertIn(f'ExecStart={self.bin}/gitea-runner daemon --config {self.config}\n', unit)
        self.assertIn(f'WorkingDirectory={self.state}\n', unit)
        self.assertNotIn('@', config + unit)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        before = (self.config.stat().st_mtime_ns, self.unit.stat().st_mtime_ns)
        again = self.setup('render')
        self.assert_ok(again)
        self.assertEqual(again.stdout.count('unchanged'), 2)
        self.assertEqual((self.config.stat().st_mtime_ns, self.unit.stat().st_mtime_ns), before)

    def test_render_replaces_a_changed_file(self):
        self.assert_ok(self.setup('render'))
        self.config.write_text('stale\n')
        result = self.setup('render')
        self.assert_ok(result)
        self.assertIn(f'wrote {self.config}', result.stdout)
        self.assertIn('factory-host:host', self.config.read_text())

    def test_render_dry_run_writes_nothing(self):
        result = self.setup('render', '--dry-run')
        self.assert_ok(result)
        self.assertIn('would write', result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_render_without_runner_binary_is_misconfiguration(self):
        (self.bin / 'gitea-runner').unlink()
        result = self.setup('render')
        self.assertEqual(result.returncode, 3)
        self.assertIn('gitea-runner not found', result.stderr)

    def test_register_passes_the_token_by_file_and_secures_the_runner_file(self):
        self.assert_ok(self.setup('render'))
        result = self.register()
        self.assert_ok(result)
        [call] = self.register_calls()
        self.assertNotIn(TOKEN_VALUE, ' '.join(call['argv']))
        self.assertIsNone(call['env_token'])
        argv = call['argv']
        self.assertEqual(argv[argv.index('--token-file') + 1], str(self.token))
        self.assertEqual(argv[argv.index('--labels') + 1], 'factory-host:host')
        self.assertEqual(argv[argv.index('--instance') + 1], 'https://gitea.example.test')
        self.assertIn('--no-interactive', argv)
        self.assertEqual(self.runner_file.stat().st_mode & 0o777, 0o600)

    def test_register_falls_back_to_the_environment_variable(self):
        self.assert_ok(self.setup('render'))
        self.assert_ok(self.register(FAKE_RUNNER_HELP='env'))
        [call] = self.register_calls()
        self.assertEqual(call['env_token'], TOKEN_VALUE)
        self.assertNotIn('--token-file', call['argv'])
        self.assertNotIn(TOKEN_VALUE, ' '.join(call['argv']))

    def test_register_refuses_when_the_token_would_need_argv(self):
        self.assert_ok(self.setup('render'))
        result = self.register(FAKE_RUNNER_HELP='none')
        self.assertEqual(result.returncode, 3)
        self.assertIn('refusing to pass the token on the command line', result.stderr)
        self.assertEqual(self.register_calls(), [])

    def test_register_rejects_a_token_file_others_can_read(self):
        self.assert_ok(self.setup('render'))
        for mode in (0o644, 0o640, 0o604):
            with self.subTest(mode=oct(mode)):
                self.token.chmod(mode)
                result = self.register()
                self.assertEqual(result.returncode, 3)
                self.assertIn('chmod 600', result.stderr)
        self.assertEqual(self.register_calls(), [])

    def test_register_rejects_missing_or_empty_token_file(self):
        self.assert_ok(self.setup('render'))
        self.token.write_text('\n')
        self.assertEqual(self.register().returncode, 3)
        self.token.unlink()
        self.assertEqual(self.register().returncode, 3)
        self.assertEqual(self.register_calls(), [])

    def test_register_is_idempotent_and_repairs_runner_file_mode(self):
        self.assert_ok(self.setup('render'))
        self.assert_ok(self.register())
        self.runner_file.chmod(0o644)
        result = self.register()
        self.assert_ok(result)
        self.assertIn('already registered', result.stdout)
        self.assertEqual(len(self.register_calls()), 1)
        self.assertEqual(self.runner_file.stat().st_mode & 0o777, 0o600)

    def test_register_redacts_a_token_echoed_by_the_runner(self):
        self.assert_ok(self.setup('render'))
        result = self.register(FAKE_RUNNER_ECHO='1')
        self.assert_ok(result)
        self.assertIn('registering with token [redacted]', result.stdout)

    def test_register_failure_is_misconfiguration(self):
        self.assert_ok(self.setup('render'))
        result = self.register(FAKE_RUNNER_FAIL='1', FAKE_RUNNER_ECHO='1')
        self.assertEqual(result.returncode, 3)
        self.assertFalse(self.runner_file.exists())

    def test_register_needs_render_first(self):
        result = self.register()
        self.assertEqual(result.returncode, 3)
        self.assertIn('run render first', result.stderr)

    def test_register_dry_run_calls_nothing(self):
        result = self.register('--dry-run')
        self.assert_ok(result)
        self.assertIn('would run (token via token-file)', result.stdout)
        self.assertEqual(self.register_calls(), [])
        self.assertFalse(self.runner_file.exists())

    def test_bad_arguments_exit_2(self):
        cases = [(), ('launch',), ('render', '--bogus'), ('render', '--name'),
                 ('register', '--token-file', str(self.token)),
                 ('register', '--instance', 'https://gitea.example.test'),
                 ('register', '--instance', 'ftp://gitea.example.test', '--token-file', str(self.token)),
                 ('register', '--instance', 'https://gitea.example.test', '--token-file', str(self.token),
                  '--name', 'bad name')]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.setup(*args).returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_enable_requires_registration_then_enables_the_user_unit(self):
        self.assert_ok(self.setup('render'))
        self.assertEqual(self.setup('enable').returncode, 3)
        self.assertEqual(self.calls('systemctl'), [])
        self.assert_ok(self.register())
        dry = self.setup('enable', '--dry-run')
        self.assert_ok(dry)
        self.assertIn('would run: systemctl --user enable --now gitea-runner-factory-host.service', dry.stdout)
        self.assertEqual(self.calls('systemctl'), [])
        result = self.setup('enable', FAKE_LINGER='no')
        self.assert_ok(result)
        self.assertEqual([c['argv'] for c in self.calls('systemctl')],
                         [['--user', 'daemon-reload'], ['--user', 'enable', '--now', 'gitea-runner-factory-host.service']])
        self.assertIn('enable-linger', result.stdout)

    def test_doctor_reports_every_missing_piece_without_changing_anything(self):
        result = self.setup('doctor', FAKE_ENABLED='disabled', FAKE_ACTIVE='inactive', FAKE_LINGER='no')
        self.assertEqual(result.returncode, 3)
        for expected in ('missing ' + str(self.config), 'not registered', 'missing ' + str(self.unit),
                         'is disabled', 'is inactive', 'pr-trigger'):
            self.assertIn(expected, result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        verbs = {c['argv'][1] for c in self.calls('systemctl')}
        self.assertEqual(verbs, {'is-enabled', 'is-active'})

    def test_doctor_passes_on_a_complete_setup(self):
        self.assert_ok(self.setup('render'))
        self.assert_ok(self.register())
        self.write_program(self.home / '.local' / 'bin' / 'pr-trigger', 'pass\n')
        result = self.setup('doctor')
        self.assert_ok(result)
        self.assertIn('looks ready', result.stdout)
        self.assertNotIn('FAIL', result.stdout)

    def test_doctor_flags_a_loose_runner_file_and_extra_container_labels(self):
        self.assert_ok(self.setup('render'))
        self.assert_ok(self.register())
        self.write_program(self.home / '.local' / 'bin' / 'pr-trigger', 'pass\n')
        self.runner_file.chmod(0o644)
        self.config.write_text(self.config.read_text().replace(
            '    - "factory-host:host"', '    - "factory-host:host"\n    - "factory-node:docker://node:22-bookworm"'))
        result = self.setup('doctor')
        self.assertEqual(result.returncode, 3)
        self.assertIn('chmod 600', result.stdout)
        self.assertIn('container label', result.stdout)
        self.assertIn('differs from the template', result.stdout)
        self.assertEqual(self.runner_file.stat().st_mode & 0o777, 0o644)

    def test_paths_follow_xdg_and_overrides(self):
        xdg = self.tmp / 'xdg-config'
        state = self.tmp / 'runner-state'
        self.assert_ok(self.setup('render', XDG_CONFIG_HOME=str(xdg), FACTORY_HOST_RUNNER_STATE_DIR=str(state)))
        self.assertTrue((xdg / 'factory-host-runner' / 'config.yaml').is_file())
        self.assertTrue((xdg / 'systemd' / 'user' / 'gitea-runner-factory-host.service').is_file())
        self.assertTrue((state / 'work').is_dir())

    def test_unsupported_paths_are_refused(self):
        result = self.setup('render', FACTORY_HOST_RUNNER_STATE_DIR=str(self.tmp / 'has space'))
        self.assertEqual(result.returncode, 3)
        self.assertIn('unsupported path', result.stderr)


class HostRunnerTemplateTests(unittest.TestCase):
    def test_templates_carry_version_comments_and_no_machine_paths(self):
        for path in sorted((ROOT / 'templates' / 'host-runner').iterdir()):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertRegex(text.splitlines()[0], r'template v\d+$')
                self.assertNotIn('/home/', text)
                self.assertNotIn('nightcrew-host', text)

    @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze not installed')
    def test_rendered_unit_is_valid_systemd_syntax(self):
        text = (ROOT / 'templates' / 'host-runner' / 'gitea-runner-factory-host.service').read_text()
        text = text.replace('@RUNNER_BIN@', '/bin/true').replace('@CONFIG@', '/tmp/c.yaml').replace('@STATE_DIR@', '/tmp')
        with tempfile.TemporaryDirectory() as tmp:
            unit = Path(tmp) / 'gitea-runner-factory-host.service'
            unit.write_text(text)
            result = subprocess.run(['systemd-analyze', '--user', 'verify', str(unit)], capture_output=True,
                                    text=True, timeout=60, env=dict(os.environ, SYSTEMD_LOG_LEVEL='err'))
            problems = [line for line in result.stderr.splitlines() if unit.name in line]
            self.assertEqual(problems, [], result.stderr)


if __name__ == '__main__':
    unittest.main()
