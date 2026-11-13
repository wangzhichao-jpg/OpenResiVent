# OpenResiVent: Residential Ventilation Calculation & Verification Toolkit

Open-source engineering software for residential fresh-air rate estimation, indoor pressure difference analysis, make-up air sizing, and duct acoustics verification.

English | [中文版 (Simplified Chinese)](README.zh-CN.md)

[![Release](https://img.shields.io/github/v/release/wangzhichao-jpg/OpenResiVent?include_prereleases&label=Release)](https://github.com/wangzhichao-jpg/OpenResiVent/releases)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)

[GitHub Repository](https://github.com/wangzhichao-jpg/OpenResiVent) · [Gitee Mirror](https://gitee.com/bigtaurus/OpenResiVent)

![OpenResiVent Full-Dwelling Ventilation Verification Wizard and Solved Results](docs/images/household_check.png)

## Intended Audience and Use Cases

- **Residential Ventilation and Building HVAC Designers**: Sizing dwelling fresh-air rates, multi-room airflow distribution, kitchen/bathroom exhaust make-up air verification, and duct hydraulic resistance.
- **Ventilation and Indoor Air Quality (IAQ) Researchers**: Multi-zone network steady-state flow simulation, crack leakage and orifice equivalent area calculation, envelope pressure difference prediction under kitchen hood exhaust, and filter dust-loading resistance decay analysis.
- **Equipment R&D and Technical Support Engineers**: Product test data processing (fan affinity laws and sensible efficiency normalization) and parametric sweep sensitivity analysis.
- **Standards Working Groups, Monograph Authors, and Educational Reviewers**: Full-dwelling verification wizard, normative clause cross-referencing, and consolidated report generation (DOCX, JSON, CSV).

## Key Features

- **Full-Dwelling Verification Wizard (`resivent check`)**: Complete fresh-air design and balance checks across dwelling zones, door/window envelope pressure differences, optional bedroom noise estimation, clause cross-checks, and report export (DOCX and JSON formats).
- **Fresh-Air Sizing and Multi-Zone Flow**: Demand sizing via air change per hour (ACH) and per-person metrics; solves steady-state well-mixed multi-zone pressure and airflow paths coupled with crack leakage and orifice equivalent areas.
- **Indoor Pressure Difference and Make-Up Air**: Predicts inter-room and envelope pressure differences under kitchen hood / bathroom exhaust fan operation, with mechanical/natural make-up air reverse sizing.
- **Duct Hydraulics and Filter Decay**: Straight pipe and local loss calculations, plus mass-conservation periodic filter dust-loading resistance decay estimation.
- **Bedroom Noise Screening**: Eight-octave band fan sound power levels from 63 Hz to 8 kHz, duct and elbow sound attenuation, and indoor A-weighted sound level prediction.
- **Parametric Sweeps (`resivent sweep`)**: Full factorial or Latin hypercube sampling, subgroup compliance rate calculation, sensitivity ranking, SQLite persistence, and export to CSV/XLSX/DOCX.
- **Product Test Processing**: Fan speed scaling and non-balanced heat exchange efficiency normalization.
- **Local Web Interface and Server**: Built-in local browser UI (`resivent serve`, bound strictly to 127.0.0.1 by default).

## Quick Start

### 1. Download and Install from Releases

Python 3.11 or higher is required. Download the pre-built wheel package from the official releases page ([GitHub Releases](https://github.com/wangzhichao-jpg/OpenResiVent/releases) or [Gitee Releases](https://gitee.com/bigtaurus/OpenResiVent/releases)):

- Asset Name: `openresivent-0.5.0rc2-py3-none-any.whl`
- SHA256 Checksum: `ea9df32cd161cddfa7df30f27710cae9b1ce68741946bd2dfa4a5a7c3d046b87`

Verify and install inside a clean virtual environment:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Verify SHA256 checksum (Linux/macOS)
echo "ea9df32cd161cddfa7df30f27710cae9b1ce68741946bd2dfa4a5a7c3d046b87  openresivent-0.5.0rc2-py3-none-any.whl" | sha256sum -c

# 3. Install the wheel
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ./openresivent-0.5.0rc2-py3-none-any.whl

# 4. Check installation version
resivent --version
```

### 2. Run Examples and Local Web Service

```bash
# Run a full-dwelling ventilation check case and generate results
resivent run cases/book/ch02/ex2-01.yaml --out results

# Launch local Web UI (listens on 127.0.0.1 by default without authentication; do not expose to public network)
resivent serve

# Execute multi-condition parametric sweep study
resivent sweep cases/studies/makeup_sweep.yaml --out results/sweep
```

## Validation and Current Status

### Algorithm Verification and Testing

Physical property routines, analytical solutions, and published literature benchmarks are monitored via automated regression tests. The second-order bounded discretization scheme for age-of-air is validated against grid sensitivity benchmarks (see [docs/site/validation.md](docs/site/validation.md)).

### Scope and Result Boundaries

This version is a public evaluation release candidate (Release Candidate), not certified design software; please verify formulas, units, parameters, and application scope before use.

Example fan curves, dwelling envelope airtightness, sound sources, duct attenuation, and environmental parameters are illustrative examples or assumptions; equal-weight parameter sweep distributions do not represent population probabilities. Weather files and external flow solvers are not bundled with the software. The complete duct acoustics path currently lacks a fully equivalent published benchmark for validation; calculation outputs cannot substitute for on-site commissioning, safety assessments, or formal design reviews.

## Documentation, Citation, and License

- **Documentation**: Refer to [User Guide](docs/site/user.md) and [Download & Installation](docs/site/下载与安装.md).
- **Citation**: If referencing this software in academic research or publications, please consult `CITATION.cff` (draft citation metadata; verify prior to formal citation).
- **License**: Core code is licensed under Apache-2.0; datasets, documentation, and benchmark cases are licensed under CC BY 4.0 (see LICENSE, NOTICE, and THIRD_PARTY_NOTICES).
- **Feedback and Issues**: Bug reports, reproducible issues, and comparative datasets are welcome via [GitHub Issues](https://github.com/wangzhichao-jpg/OpenResiVent/issues) or [Gitee Issues](https://gitee.com/bigtaurus/OpenResiVent/issues). Please do not upload private or unauthorized personal data.
