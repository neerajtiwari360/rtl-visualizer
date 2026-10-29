# RTL Workbench

A general local Verilog / SystemVerilog visualization and analysis tool. The main page is a multi-file workbench; Conv2D remains a separate guided example at `/examples/conv2d`.

## Start the workbench

```powershell
docker compose up -d --build
```

Open http://localhost:8000 and load the counter example or import your own RTL files. Set **Design top** to your synthesizable module and **Simulation top** to your testbench module.

- **Lint:** Verilator diagnostics for the design hierarchy. Completion can include warnings; inspect the log.
- **Synthesize:** Yosys optimized RTL schematic, module ports, net counts, cell counts and cell types.
- **Simulate:** Verilator execution, testbench assertions and generic VCD waveforms.
- **Run all:** runs each stage independently and reports errors separately.

Add or import multiple `.v` / `.sv` files. Set synthesizable sources to **Design**, testbench sources to **Testbench**, and include headers / memory files to **Header / data**. Source order follows the file list (put packages before modules that import them). Filenames are flat: use `include "header.svh"` rather than nested directories. Export and restore projects as JSON to retain edits; browser edits do not update disk files.

Simulation requires a testbench with stimulus and a terminating `$finish`. Add `$dumpfile("trace.vcd"); $dumpvars(0, tb_name);` to record signals. Use assertions or `$fatal` for expected behavior. A successful simulation means the executable finished without errors; correctness depends on the checks you supply.

The waveform viewer displays actual recorded transitions. Select up to 32 signals, filter names, zoom and pan, and inspect values at a time cursor. Numeric formats include binary, hex, unsigned and two's-complement signed. Time labels use raw VCD ticks with the VCD timescale shown. Display limits are 512 signals and 100,000 value changes; dense transitions are condensed. Download the original VCD for a full trace. VCD files above 8 MiB are rejected for display.

Download the SVG circuit, JSON netlist, VCD and stage analysis report. Yosys supports a synthesizable subset of SystemVerilog; unsupported constructs can simulate successfully while synthesis fails. Statistics are before technology mapping and do not predict physical area, power or timing. VHDL and formal verification are not supported by this setup.

Projects support up to 24 files, 64,000 characters each and a 2 MiB request limit. Compile and synthesis stages have 90-second timeouts; simulation has a 10-second wall-clock timeout. One job runs at a time.

## Tests

```powershell
docker compose exec rtl-visualizer python -m unittest discover -s tests -v
```

Tests cover VCD decoding, input validation, independent stage failures, the generic counter flow and Conv2D regression cases. Docker / Python / the RTL toolchain are unavailable in the authoring environment, so these tests must be run in the container.

## Conv2D guided example

Flask, Verilator, Yosys, Graphviz and NumPy in a single local Docker container.

```powershell
cd D:\Github\rtl-visualizer
docker compose up -d --build
```

Open http://localhost:8000 in Chrome or Edge. Docker Desktop must use Linux containers. The first build downloads the toolchain and dependencies.

Edit input values or RTL, run simulation, scrub or play the MAC waveform, compare NumPy results and zoom the circuit schematic. Download the VCD, SVG schematic and JSON netlist. Compiler errors appear in the browser.

## Design contract

- Signed 8-bit 4×4 input and 3×3 kernel; stride 1; no padding or bias.
- Valid cross-correlation: the kernel is not flipped.
- Four signed 32-bit outputs, row-major, nine MAC cycles each.
- Packed input bytes are row-major, first element in the least significant byte.
- Preserve the `conv2d` ports when editing. Pulse `start` while idle; `valid` pulses per output. `done` stays high until reset or another start.
- The explorer samples operands and accumulator before the active MAC edge. Output results are sampled after the edge. Download the VCD for full reset and handshake waveforms.
- The schematic shows optimized RTL, before technology mapping or physical implementation.

Browser edits are temporary; reload restores `rtl/conv2d.sv`. Edit that file to persist changes. The RTL folder is mounted read-only in the container. Rebuild for Python or HTML changes.

This is a local development application for trusted RTL. It compiles and executes edited code inside the container. Do not expose it publicly or use untrusted RTL. One job runs at a time with timeouts. Flask's development server serves local requests.

## Validation

The default input should produce four `-6` outputs and 36 MAC cycles. Also try a zero kernel, negative inputs and signed extrema. Invalid syntax should display the compiler error. `/api/health` reports tool availability.

Toolchain execution has not been verified in the authoring session because Docker, Python, Verilator and Yosys were unavailable on PATH.

Run end-to-end regression tests inside the container (default kernel, final memory entries and signed accumulation):

```powershell
docker compose exec rtl-visualizer python -m unittest discover -s tests -v
```

```powershell
docker compose logs -f
docker compose down
```
