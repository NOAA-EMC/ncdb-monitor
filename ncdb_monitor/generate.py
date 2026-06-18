import logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

import os
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime, time
import re
import json
import hashlib
from ncdb.api.database import Database
from ncdb_monitor.config import WEBSITE_DATA_FILE

# --- CONFIGURATION CONTROLS ---
GENERATE_SNAPSHOTS = False  # Toggle this to False to skip the heavy 2D map generation
# ------------------------------

def safe_name(name: str) -> str:
    """
    Convert a variable/obsspace name into a filesystem-safe filename.
    """
    name = name.replace("/", "_").replace(" ", "_")
    name = re.sub(r"[^a-zA-Z0-9_.-]", "", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def load_latest_run(website_dir):
    runs_dir = Path(website_dir) / "runs"
    if not runs_dir.exists():
        return None
    run_files = sorted(runs_dir.glob("*.json"))
    if not run_files:
        return None
    with open(run_files[-1]) as f:
        return json.load(f)


def get_preview_variable(obsspace, obsspace_info):
    for var in obsspace_info["variables"]:
        if "nobs" in var["metrics"]:
            return var
    return None


def generate_time_series_plots(obsspace, metric_name, plot_dir):
    plots = []
    obsspace_name = obsspace.name
    variables = obsspace.list_variables(group="ObsValue")

    for var in variables:
        try:
            field = obsspace.field(var)
            metric = getattr(field, metric_name)
        except Exception as e:
            logger.debug(f"Skipping {obsspace_name}:{var} metric={metric_name} due to {e}")
            continue

        out_file = safe_name(var) + ".png"
        plot_path = os.path.join(plot_dir, out_file)
        logger.info(f"Generating {metric_name} plot {plot_path}")

        try:
            metric.plot(plot_path)
        except Exception as e:
            logger.debug(f"Failed plotting {obsspace_name}:{var} metric={metric_name} due to {e}")
            continue

        plots.append({
            "variable": var,
            "path": out_file
        })
    return plots


def generate_snapshot_plots(field, plot_dir, n_latest_cycles=4):
    plots = []
    try:
        cycles = field.cycles()
    except Exception as e:
        logger.debug(f"Could not get cycles due to {e}")
        return plots

    latest_cycles = cycles[-n_latest_cycles:]

    for t in latest_cycles:
        try:
            value = field[t]
        except Exception as e:
            logger.debug(f"Skipping snapshot time={t} due to {e}")
            continue

        cycle_string = t.strftime("%Y%m%d%H")
        out_file = safe_name(cycle_string) + ".png"
        plot_path = os.path.join(plot_dir, out_file)

        logger.info(f"Generating snapshot {plot_path}")
        try:
            value.plot(plot_path)
        except Exception as e:
            logger.debug(f"Failed plotting time={t} due to {e}")
            continue

        plots.append({
            "cycle": t.strftime("%Y-%m-%d %H:%M"),
            "path": out_file
        })
    return plots


def generate_obsspace_data(
    dataset_name,
    obsspace,
    dataset_dir,
    metric_names,
    dataset_dir_name=None,
    generate_snapshots=True  # Added parameter flag
):
    if dataset_dir_name is None:
        dataset_dir_name = dataset_name

    obsspace_name = obsspace.name
    logger.info(f"Processing obsspace {obsspace_name}")

    obsspace_safe_name = safe_name(obsspace_name)
    obsspace_dir = os.path.join(dataset_dir, obsspace_safe_name)
    os.makedirs(obsspace_dir, exist_ok=True)

    obsspace_info = {
        "name": obsspace_name,
        "safe_name": obsspace_safe_name,
        "variables": []
    }

    # Generate time-series metrics
    metric_plots = {}
    for metric_name in metric_names:
        metric_dir = os.path.join(obsspace_dir, metric_name)
        os.makedirs(metric_dir, exist_ok=True)
        metric_plots[metric_name] = generate_time_series_plots(obsspace, metric_name, metric_dir)

    # Per-variable processing
    variables = obsspace.list_variables(group="ObsValue")
    for var in variables:
        logger.info(f"Processing variable {obsspace_name}:{var}")
        variable_info = {
            "name": var,
            "metrics": {},
            "snapshots": []
        }

        # Map metric plots
        for metric_name in metric_names:
            for plot in metric_plots[metric_name]:
                if plot["variable"] != var:
                    continue
                variable_info["metrics"][metric_name] = {
                    "path": f"{dataset_dir_name}/{obsspace_safe_name}/{metric_name}/{plot['path']}",
                    "local_path": f"{metric_name}/{plot['path']}"
                }


        # Extract the real numerical observation count from the database for the preview column
        try:
            field = obsspace.field(var)
            nobs_field = field.nobs
            nobs_cycles = nobs_field.cycles
            if nobs_cycles:
                latest_cycle = nobs_cycles[-1]
                # Evaluate the scalar value at the most recent database cycle entry
                variable_info["last_nobs_value"] = int(nobs_field[latest_cycle].data)
        except Exception as e:
            logger.debug(f"Could not extract numerical observation count for {var}: {e}")


        # CONDITIONAL OPTIONAL GENERATION: 2D Snapshot Maps
        if generate_snapshots:
            try:
                field = obsspace.field(var)
            except Exception as e:
                logger.debug(f"Skipping field {obsspace_name}:{var} due to {e}")
                continue

            snapshots_dir = os.path.join(obsspace_dir, "snapshots", safe_name(var))
            os.makedirs(snapshots_dir, exist_ok=True)

            snapshot_plots = generate_snapshot_plots(field, snapshots_dir)
            for plot in snapshot_plots:
                variable_info["snapshots"].append({
                    "cycle": plot["cycle"],
                    "path": f"{dataset_dir_name}/{obsspace_safe_name}/snapshots/{safe_name(var)}/{plot['path']}",
                    "local_path": f"snapshots/{safe_name(var)}/{plot['path']}"
                })
        else:
            logger.debug(f"Snapshot generation disabled. Skipping 2D maps for {var}.")

        obsspace_info["variables"].append(variable_info)

    preview_var = get_preview_variable(obsspace, obsspace_info)
    obsspace_info["preview_variable"] = preview_var

    return obsspace_info


def generate_website_data(db, website_dir, generate_snapshots=True):
    raw_run = load_latest_run(website_dir)
    
    # Clean up the timestamp format for the top bar right at the data ingestion point
    if raw_run and "end_time" in raw_run:
        try:
            clean_time = raw_run["end_time"].replace('Z', '+00:00')
            dt = datetime.fromisoformat(clean_time)
            raw_run["end_time"] = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    website_data = {
        "meta": {
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "database_file": str(db.path),
            "has_snapshots": generate_snapshots,
        },
        "run": raw_run,
        "datasets": []
    }

    metric_names = ["nobs", "mean"]

    for dataset in db.datasets():
        dataset_name = dataset.name
        logger.info(f"Processing dataset {dataset_name}")

        if hasattr(dataset, "id") and dataset.id is not None:
            dataset_dir_name = f"{dataset_name}_id{dataset.id}"
        else:
            root_hash = hashlib.md5(str(dataset.root_dir).encode("utf-8")).hexdigest()[:8]
            dataset_dir_name = f"{dataset_name}_{root_hash}"

        dataset_dir = os.path.join(website_dir, dataset_dir_name)
        os.makedirs(dataset_dir, exist_ok=True)

        # Safely extract and format available cycle strings for this dataset
        ds_cycles = []
        if hasattr(dataset, "cycles"):
            for c in dataset.cycles:
                if isinstance(c, datetime):
                    ds_cycles.append(c.strftime("%Y-%m-%d %H:%M"))
                else:
                    ds_cycles.append(str(c))
        ds_cycles = sorted(list(set(ds_cycles)))

        dataset_info = {
            "name": dataset_name,
            "root_dir": dataset.root_dir,
            "dir_name": dataset_dir_name,
            "cycles": ds_cycles,  # Exposed directly to templates/index.html
            "obsspaces": []
        }

        obsspace_names = [n.name for n in dataset.obsspaces()]
        for obsspace_name in obsspace_names:
            obsspace = dataset.obsspace(obsspace_name)
            obsspace_info = generate_obsspace_data(
                dataset_name,
                obsspace,
                dataset_dir,
                metric_names,
                dataset_dir_name=dataset_dir_name,
                generate_snapshots=generate_snapshots
            )
            dataset_info["obsspaces"].append(obsspace_info)

        website_data["datasets"].append(dataset_info)

    website_data_file = os.path.join(website_dir, WEBSITE_DATA_FILE)
    with open(website_data_file, "w") as f:
        json.dump(website_data, f, indent=2)
        
    return website_data

def oldgenerate_website_data(db, website_dir, generate_snapshots=True):
    website_data = {
        "meta": {
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "database_file": str(db.path),
            "has_snapshots": generate_snapshots,  # Exposed dynamically to UI templates
        },
        "run": load_latest_run(website_dir),
        "datasets": []
    }

    metric_names = ["nobs", "mean"]

    for dataset in db.datasets():
        dataset_name = dataset.name
        logger.info(f"Processing dataset {dataset_name}")

        if hasattr(dataset, "id") and dataset.id is not None:
            dataset_dir_name = f"{dataset_name}_id{dataset.id}"
        else:
            root_hash = hashlib.md5(str(dataset.root_dir).encode("utf-8")).hexdigest()[:8]
            dataset_dir_name = f"{dataset_name}_{root_hash}"

        dataset_dir = os.path.join(website_dir, dataset_dir_name)
        os.makedirs(dataset_dir, exist_ok=True)

        dataset_info = {
            "name": dataset_name,
            "root_dir": dataset.root_dir,
            "dir_name": dataset_dir_name,
            "obsspaces": []
        }

        obsspace_names = [n.name for n in dataset.obsspaces()]
        for obsspace_name in obsspace_names:
            obsspace = dataset.obsspace(obsspace_name)
            obsspace_info = generate_obsspace_data(
                dataset_name,
                obsspace,
                dataset_dir,
                metric_names,
                dataset_dir_name=dataset_dir_name,
                generate_snapshots=generate_snapshots  # Passed down to control execution
            )
            dataset_info["obsspaces"].append(obsspace_info)

        website_data["datasets"].append(dataset_info)

    website_data_file = os.path.join(website_dir, WEBSITE_DATA_FILE)
    with open(website_data_file, "w") as f:
        json.dump(website_data, f, indent=2)
        
    return website_data


def main():
    db = Database("emcda.db")
    logger.info(db.list_datasets())

    website_dir = "./website"
    
    # Generate the underlying tracking data structure conditionally
    website_data = generate_website_data(db, website_dir, generate_snapshots=GENERATE_SNAPSHOTS)
    
    # Pass down the dataset representation dictionary cleanly
    generate_html(
        website_data,
        website_dir
    )

if __name__ == "__main__":
    main()
