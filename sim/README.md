# sim

Simulation base for SG13G2: a pinned PDK, OSDI device models built from the
PDK's own Verilog-A, and a smoke simulation proving the toolchain end to end.
Spec values (bitcell device, supply, swing, corners) live in `spec/`, not here.

## Layout

- `pdk.json`: pinned IHP-Open-PDK release and tarball sha256.
- `harness/common/tools/build-osdi.sh`, `harness/common/env.sh`: vendored
  byte-identical from `2AMLogic/sg13g2-bandgap` (see `../reuse.lock.json`).
  Their echo hints mention `sim/tools/build-osdi.sh` and `sim/env.sh`; the real
  paths are the ones here.
- `pdk-smoke/`: smoke runner and append-only records under `records/<UTC>/`.
- `bitcell/`: 6T bitcell hold/read SNM and write margin over the 45 corners
  (`bitcell/README.md`).
- `column/`: nominal read/write bench of the I/O column (`column/README.md`).
- `array/`: in-situ read SNM, write margin through the real write driver, access time and
  write completion over the 45 corners (`array/README.md`).
- `run_all.sh`: the cold-start invocation of every claimed measurement (T1 item 9,
  `attest/item9.json`).

## Cold start (Linux x86_64)

IHP-Open-PDK v0.3.0 ships the PSP103 MOS models as Verilog-A source only, so no
MOS device simulates until an `.osdi` build exists. The PDK and the `.osdi`
output live outside the repo (never committed).

```bash
# 1. fetch the pinned PDK (tarball sha256 is in sim/pdk.json)
export PDK_ROOT="$(mktemp -d)" PDK=ihp-sg13g2
curl -fsSL -o "$PDK_ROOT/pdk.tgz" \
  https://github.com/IHP-GmbH/IHP-Open-PDK/archive/refs/tags/v0.3.0.tar.gz
echo "f6afb7a8d2adf3e40acd3fd2c7892fc93510e6f760565409a8df2b5b242254fc  $PDK_ROOT/pdk.tgz" | sha256sum -c -
mkdir -p "$PDK_ROOT/$PDK"
tar xzf "$PDK_ROOT/pdk.tgz" --strip-components=2 -C "$PDK_ROOT/$PDK" IHP-Open-PDK-0.3.0/ihp-sg13g2/

# 2. build the OSDI models (pinned OpenVAF-Reloaded; idempotent, --check verifies)
sim/harness/common/tools/build-osdi.sh

# 3. smoke: four devices, DC op + Id-Vgs, mos_tt, 27 C; exits non-zero on non-convergence
sim/pdk-smoke/run_smoke.sh
```

(`klayout-tools`' `scripts/fetch-ihp-sg13g2.sh` is an equivalent fetch for step 1.)

**ngspice must be 43 or newer.** OpenVAF-Reloaded emits OSDI v0.4; ngspice-42
(Ubuntu 24.04's `/usr/bin/ngspice`) only supports v0.3 and refuses to load the
models. Put a newer ngspice on `PATH` (build it from source into a throwaway
prefix if the host's is old). `build-osdi.sh` caches its compiler under
`~/.cache/sg13g2-bandgap`; set `SG13G2_TOOLS_CACHE` to redirect it.

## Smoke records

Each run writes a new `pdk-smoke/records/<UTC>/` (netlists, per-device logs and
sweep data, `record.json` with PDK tag, OpenVAF-R and ngspice versions). Records
are append-only evidence: never edit or overwrite one; add a new run.
