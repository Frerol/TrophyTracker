# Developer tools

- `checks/`: CI helper scripts. `packaging_smoke.py` starts a frozen build with
  an isolated data directory and verifies it initializes.
- `benchmarks/`: repeatable performance probes. Run from the repository root
  with the project's environment and `PYTHONPATH=src`.
- `rahasher/`: optional third-party helper and its redistribution notices.
  Keep the binary, `RAHasher-COPYING.txt` and `RAHasher-SOURCE.txt` together.
  The committed helper is for Windows; Linux builds need a native `RAHasher`
  in the same directory or use the application's built-in hashing.

Explorer/hash/artwork benchmark (temporary data, no live API):

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python tools/benchmarks/benchmark_explorer.py
```

Results and method are described in
[performance validation](../docs/validation/PerformanceValidation.md).
Build scripts and the PyInstaller spec are in
[`packaging/`](../packaging/README.md).

At runtime, `RETROCHEEVOS_RAHASHER` overrides helper discovery. The application
also checks `tools/rahasher/` in source/frozen installs, legacy `tools/` locations
and the system PATH. No helper is downloaded automatically.
