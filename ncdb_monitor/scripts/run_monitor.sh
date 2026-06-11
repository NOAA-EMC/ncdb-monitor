#!/bin/bash
set -e

DATABASE="cp4.03-parqllel-3dvar.db"
WEBSITE_DIR="./website"
DATA_DIR="/scratch4/NCEPDEV/global/John.Steffen/hpss_arch/cp4.03-parallel-3dvar"
SCANNER="marine"
NUMBER_OF_CYCLES=-1
# PORT_NUMBER=8734

ncdb-monitor run \
    --database "$DATABASE" \
    --scanner "$SCANNER" \
    --data-dir "$DATA_DIR" \
    --n-cycles "$NUMBER_OF_CYCLES" \
    --website-dir "$WEBSITE_DIR"

exit

echo "=== SCAN ==="
ncdb-monitor scan \
	--database  "$DATABASE" \
	--scanner "$SCANNER" \
	--data-dir "$DATA_DIR" \
	--n-cycles "$NUMBER_OF_CYCLES"

echo "=== GENERATE ==="
ncdb-monitor generate \
	--database  "$DATABASE" \
	--website-dir "$WEBSITE_DIR"

echo "=== RENDER ==="
ncdb-monitor render \
	--website-dir "$WEBSITE_DIR"

# echo "=== SERVE ==="
# python -m monitor.cli serve \
	# --website-dir "$WEBSITE_DIR" \
    # --port "$PORT_NUMBER"
