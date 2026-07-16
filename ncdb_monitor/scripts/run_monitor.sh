#!/bin/bash -l

# 1. Use the script's actual location dynamically
MONITOR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV="${MONITOR_DIR}/venv"
DATABASE="${MONITOR_DIR}/emcda.db"
WEBSITE_DIR="${MONITOR_DIR}/emcda_website"
LOG_FILE="${MONITOR_DIR}/cron_monitor.log"
LOCK_FILE="${MONITOR_DIR}/monitor.lock"

RZDM_WEB_DIR="/home/people/emc/ftp/obsforge_website"
RZDM_ADDRESS="egivelberg@emcrzdm:${RZDM_WEB_DIR}/"
SSH_KEY="${HOME}/.ssh/id_rsa"

DATA_ROOT="/lfs/h2/emc/da/noscrub/emc.da/obsForge/COMROOT/realtime"
N_CYCLES=-1

# Exit immediately if any command fails
set -e

# --- Prevent concurrent runs using flock ---
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Warning: Another instance of run_monitor.sh is already running. Exiting."
    exit 0
fi

{
    echo "Initializing Environment: $(date)"

    module purge
    module load envvar/1.0
    module load intel/19.1.3.304
    module load python/3.12.0
    module load geos/3.8.1
    module load proj/7.1.0

    # Double-check that the venv actually exists before trying to source it
    if [ ! -f "${VENV}/bin/activate" ]; then
        echo "ERROR: Virtual environment not found at ${VENV}" >&2
        exit 1
    fi
    source "${VENV}/bin/activate"
    echo "Activated virtual environment $VENV"

    echo "=================================================="
    echo "Starting Monitor Pipeline: $(date)"
    echo "Data Dir: $DATA_ROOT"
    echo "Database: $DATABASE"
    echo "Cycle Limit: $N_CYCLES"
    echo "Website: $WEBSITE_DIR"
    echo "=================================================="

    # --- PREVENTION 2: Force termination if it takes longer than 2 hours ---
    timeout -k 5m 2h ncdb-monitor run \
      --database "${DATABASE}" \
      --scanner obsforge_marine \
      --data-dir "${DATA_ROOT}" \
      --n-cycles "${N_CYCLES}" \
      --website-dir "${WEBSITE_DIR}"

    echo "$(date): Uploading website to ${RZDM_ADDRESS}"

    # Force a 10-minute maximum limit on the scp process just in case the network connection hangs
    timeout 10m scp -i "${SSH_KEY}" -qp -r "${WEBSITE_DIR}/"* "${RZDM_ADDRESS}"

    echo "=================================================="
    echo "Monitor Pipeline complete: $(date)"
    echo "=================================================="

} >> "$LOG_FILE" 2>&1

# --- ANYTHING BELOW THIS LINE ESCAPES THE LOG FILE AND GOES TO CRON MAIL ---
echo "ObsForge Monitor completed a run at $(date)."
echo "Tail of the log file:"
tail -n 25 "$LOG_FILE"
