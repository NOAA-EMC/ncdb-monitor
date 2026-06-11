# ncdb-monitor

Monitoring dashboard for NCDB datasets.

## Features

- Scan observational datasets
- Generate diagnostic plots (nobs, mean, etc.)
- Render static HTML dashboard
- Run full pipeline via CLI

## Usage

```bash
ncdb-monitor run \
  --database cp4.03-parqllel-3dvar.db \
  --scanner marine \
  --data-dir /path/to/data \
  --n-cycles -1 \
  --website-dir ./website
