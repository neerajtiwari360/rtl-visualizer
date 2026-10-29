"""Generic project validation, VCD decoding and toolchain orchestration."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*')
FILENAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:sv|v|svh|vh|hex|mem)')


def parse_vcd(text):
    scopes, signals, codes = [], [], {}
    tokens = iter(text.split())
    time, end_time, timescale, event_count = 0, 0, '', 0
    truncated = False
    for token in tokens:
        if token == '$scope':
            next(tokens, ''); scopes.append(next(tokens, ''))
        elif token == '$upscope':
            if scopes:
                scopes.pop()
        elif token == '$timescale':
            parts = []
            for part in tokens:
                if part == '$end':
                    break
                parts.append(part)
            timescale = ' '.join(parts)
        elif token == '$var':
            kind, width, code, name = (next(tokens, '') for _ in range(4))
            suffix = []
            for part in tokens:
                if part == '$end':
                    break
                suffix.append(part)
            if len(signals) < 512:
                changes = codes.setdefault(code, [])
                signals.append(dict(name='.'.join(scopes + [name]) + ''.join(suffix),
                                    width=int(width), kind=kind, changes=changes))
            else:
                truncated = True
        elif token.startswith('#'):
            time = int(token[1:]); end_time = max(end_time, time)
        elif token and token[0].lower() in '01xzbr':
            if token[0].lower() in 'br':
                value, code = token[1:], next(tokens, '')
            else:
                value, code = token[0], token[1:]
            if code in codes:
                if event_count < 100000:
                    codes[code].append([time, value]); event_count += 1
                else:
                    truncated = True
        elif token.startswith('$') and token not in ('$end', '$dumpvars', '$dumpall', '$dumpon', '$dumpoff'):
            for part in tokens:
                if part == '$end':
                    break
    return dict(signals=signals, end_time=end_time, timescale=timescale, truncated=truncated)


def validate_project(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON project object.')
    files = data.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 24:
        raise ValueError('Provide between 1 and 24 project files.')
    names = set()
    for file in files:
        if not isinstance(file, dict):
            raise ValueError('Invalid file entry.')
        name, content = file.get('name'), file.get('content')
        if not isinstance(name, str) or not FILENAME.fullmatch(name) or '..' in name or name in names:
            raise ValueError('Use unique plain filenames ending in .sv, .v, .svh, .vh, .hex or .mem.')
        if not isinstance(content, str) or len(content) > 64000:
            raise ValueError('Each file must contain at most 64,000 characters.')
        if file.get('role') not in ('design', 'testbench', 'data'):
            raise ValueError('Each file needs a design, testbench or data role.')
        names.add(name)
    for key in ('top', 'sim_top'):
        if not isinstance(data.get(key), str) or not IDENTIFIER.fullmatch(data[key]):
            raise ValueError(f'{key} must be a simple Verilog module identifier.')
    action = data.get('action', 'all')
    if action not in ('all', 'lint', 'synthesis', 'simulation'):
        raise ValueError('Unknown analysis action.')
    return files, action


def analyze_project(data, command):
    files, action = validate_project(data)
    design = [f['name'] for f in files if f['role'] == 'design' and f['name'].endswith(('.sv', '.v'))]
    testbench = [f['name'] for f in files if f['role'] == 'testbench' and f['name'].endswith(('.sv', '.v'))]
    if not design:
        raise ValueError('Add at least one design .sv or .v file.')
    result = dict(stages={}, waveform=None, schematic=None, netlist=None, vcd=None, modules=[])
    with tempfile.TemporaryDirectory(prefix='rtl-lab-') as tmp:
        work = Path(tmp)
        for file in files:
            (work / file['name']).write_text(file['content'], encoding='utf-8')

        def stage(name, fn):
            try:
                result['stages'][name] = dict(ok=True, log=fn()[-24000:])
            except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                result['stages'][name] = dict(ok=False, log=str(exc)[-24000:])

        if action in ('all', 'lint'):
            stage('lint', lambda: command(['verilator', '--lint-only', '--timing', '-Wall', '-Wno-fatal',
                                          '--top-module', data['top'], *design], work))
        if action in ('all', 'synthesis'):
            def synthesis():
                script = ('read_verilog -sv ' + ' '.join(design) + '; hierarchy -check -top ' + data['top']
                          + '; proc; opt; check; stat; write_json netlist.json; show -format svg -prefix circuit ' + data['top'])
                log = command(['yosys', '-p', script], work)
                result['netlist'] = (work / 'netlist.json').read_text()
                for name, module in json.loads(result['netlist'])['modules'].items():
                    counts = {}
                    for cell in module.get('cells', {}).values():
                        counts[cell['type']] = counts.get(cell['type'], 0) + 1
                    result['modules'].append(dict(name=name, ports=module.get('ports', {}),
                                                   cells=counts, net_count=len(module.get('netnames', {}))))
                result['schematic'] = (work / 'circuit.svg').read_text()
                return log
            stage('synthesis', synthesis)
        if action in ('all', 'simulation'):
            def simulate():
                if not testbench:
                    raise ValueError('Add a testbench with stimulus, $dumpfile("trace.vcd"), $dumpvars and $finish.')
                build = command(['verilator', '--binary', '--timing', '--trace', '--assert', '-Wno-fatal',
                                 '--top-module', data['sim_top'], *design, *testbench, '-j', '2'], work)
                log = command([str(work / 'obj_dir' / ('V' + data['sim_top']))], work, 10)
                vcd = work / 'trace.vcd'
                if vcd.exists():
                    if vcd.stat().st_size > 8 * 1024 * 1024:
                        raise ValueError('VCD exceeds the 8 MiB display limit. Shorten the simulation or reduce dump scope.')
                    result['vcd'] = vcd.read_text()
                    result['waveform'] = parse_vcd(result['vcd'])
                else:
                    log += '\nNo trace.vcd generated. Add $dumpfile("trace.vcd") and $dumpvars to the testbench.'
                return build + '\n' + log
            stage('simulation', simulate)
    return result
