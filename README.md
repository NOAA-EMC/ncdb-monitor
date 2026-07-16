# ncdb-monitor

Monitoring dashboard for NCDB datasets.

## Features

- Scan observational datasets
- Generate diagnostic plots (nobs, mean, etc.)
- Render static HTML dashboard
- Run full pipeline via CLI

## Installation

### Normal Installation

1. Create and activate environment
```bash
python -m venv venv
source venv/bin/activate
```

2. Install directly from GitHub (this will install ncdb)
```bash
pip install git+[https://github.com/NOAA-EMC/ncdb-monitor.git](https://github.com/NOAA-EMC/ncdb-monitor.git)
```


### WCOSS2 Installation

1. Load WCOSS2 Modules

```bash
module purge
module load envvar/1.0
module load intel/19.1.3.304
module load python/3.12.0
module load geos/3.8.1
module load proj/7.1.0
```

2. Set Path Variables

```bash
GEOS_PATH="/apps/prod/hpc-stack/intel-19.1.3.304/geos/3.8.1"

export CFLAGS="-I${GEOS_PATH}/include"
export CXXFLAGS="-I${GEOS_PATH}/include"
export LDFLAGS="-L${GEOS_PATH}/lib"
export PATH="${GEOS_PATH}/bin:${PATH}"
export CC=cc
export CXX=CC
```

3. Create Virtual Environment and Install
```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

4. Install
```bash
pip install git+[https://github.com/NOAA-EMC/ncdb.git](https://github.com/NOAA-EMC/ncdb.git)
pip install --no-deps git+[https://github.com/NOAA-EMC/ncdb-monitor.git](https://github.com/NOAA-E
```

## Usage

```bash
ncdb-monitor run \
  --database cp4.03-parqllel-3dvar.db \
  --scanner marine \
  --data-dir /path/to/data \
  --n-cycles -1 \
  --website-dir ./website
```

See also an example script running the monitor
in a cron job and uploading the website to RZDM:
```bash
ncdb-monitor/ncdb_monitor/scripts/run_monitor.sh
```
