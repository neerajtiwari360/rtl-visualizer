"""Local, single-user RTL lab. Uploaded RTL executes inside the Docker container."""
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
from flask import Flask, jsonify, render_template, request
from rtl_analysis import analyze_project

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
job_lock = threading.Lock()


def command(args, directory, timeout=90):
    proc = subprocess.run(args, cwd=directory, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout)
    if proc.returncode:
        raise ValueError(proc.stdout[-12000:])
    return proc.stdout


def matrix(value, rows, cols, name):
    if not isinstance(value, list) or len(value) != rows or any(
        not isinstance(row, list) or len(row) != cols for row in value
    ):
        raise ValueError(f'{name} must be {rows}×{cols}.')
    if any(type(x) is not int or not -128 <= x <= 127 for row in value for x in row):
        raise ValueError(f'{name} values must be integers from -128 to 127.')
    return np.array(value, dtype=np.int64)


@app.get('/')
def index():
    return render_template('generic.html')


@app.get('/examples/conv2d')
def conv2d_example():
    return render_template('index.html')


@app.post('/api/analyze')
def analyze():
    if not job_lock.acquire(blocking=False):
        return jsonify(error='Another job is running.'), 409
    try:
        return jsonify(analyze_project(request.get_json(), command))
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return jsonify(error=str(exc)), 400
    finally:
        job_lock.release()


@app.get('/api/example/<name>')
def example(name):
    if name not in ('counter', 'conv2d'):
        return jsonify(error='Unknown example.'), 404
    files = [dict(name=f'{name}.sv', role='design', content=(ROOT / f'rtl/{name}.sv').read_text()),
             dict(name=f'tb_{name}.sv', role='testbench', content=(ROOT / f'rtl/tb_{name}.sv').read_text())]
    if name == 'conv2d':
        files += [dict(name='pixels.hex', role='data', content='\n'.join(f'{x:02x}' for x in range(1, 17)) + '\n'),
                  dict(name='weights.hex', role='data', content='01\n00\nff\n01\n00\nff\n01\n00\nff\n')]
    return jsonify(files=files, top=name, sim_top=f'tb_{name}')


@app.get('/api/source')
def source():
    return jsonify(source=(ROOT / 'rtl/conv2d.sv').read_text())


@app.get('/api/health')
def health():
    return jsonify(tools={name: bool(shutil.which(name)) for name in ['verilator', 'yosys', 'dot']})


@app.post('/api/run')
def run():
    if not job_lock.acquire(blocking=False):
        return jsonify(error='A simulation is already running.'), 409
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')
        pixels = matrix(data.get('pixels'), 4, 4, 'Input')
        weights = matrix(data.get('weights'), 3, 3, 'Kernel')
        rtl = data.get('source')
        if not isinstance(rtl, str) or not rtl.strip() or len(rtl) > 64000:
            raise ValueError('Provide RTL source up to 64,000 characters.')
        with tempfile.TemporaryDirectory(prefix='conv2d-') as tmp:
            work = Path(tmp)
            (work / 'conv2d.sv').write_text(rtl)
            shutil.copy(ROOT / 'rtl/tb_conv2d.sv', work)
            for name, values in [('pixels', pixels), ('weights', weights)]:
                # Terminate every memory word, including the final one, for $readmemh.
                (work / f'{name}.hex').write_text('\n'.join(f'{int(x) & 255:02x}' for x in values.flat) + '\n')
            build = command(['verilator', '--binary', '--timing', '--trace', '-Wno-fatal',
                             '--top-module', 'tb_conv2d', 'conv2d.sv', 'tb_conv2d.sv', '-j', '2'], work)
            log = command([str(work / 'obj_dir/Vtb_conv2d')], work, 10)
            trace, outputs = [], {}
            for line in log.splitlines():
                if re.fullmatch(r'MAC(?: -?\d+){7}', line):
                    trace.append(dict(zip(['cycle', 'index', 'tap', 'pixel', 'weight', 'product', 'accumulator'],
                                          map(int, line.split()[1:]))))
                if re.fullmatch(r'OUT \d+ -?\d+', line):
                    _, idx, value = line.split()
                    if int(idx) in outputs:
                        raise ValueError('RTL emitted a duplicate output index.')
                    outputs[int(idx)] = int(value)
            expected = [int(np.sum(pixels[r:r+3, c:c+3] * weights)) for r in range(2) for c in range(2)]
            verification = [dict(index=i, expected=v, actual=outputs.get(i), passed=outputs.get(i) == v)
                            for i, v in enumerate(expected)]
            schematic, synthesis_error = None, None
            try:
                command(['yosys', '-p', 'read_verilog -sv conv2d.sv; hierarchy -check -top conv2d; proc; opt; write_json netlist.json; show -format svg -prefix circuit conv2d'], work)
                schematic = (work / 'circuit.svg').read_text()
            except (ValueError, subprocess.TimeoutExpired) as exc:
                synthesis_error = str(exc)
            return jsonify(trace=trace, verification=verification, schematic=schematic,
                           synthesis_error=synthesis_error, log=(build + '\n' + log)[-16000:],
                           vcd=(work / 'trace.vcd').read_text(),
                           netlist=(work / 'netlist.json').read_text() if (work / 'netlist.json').exists() else None)
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return jsonify(error=str(exc)), 400
    finally:
        job_lock.release()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)
