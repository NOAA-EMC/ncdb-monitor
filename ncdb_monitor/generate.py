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
import matplotlib.pyplot as plt

from ncdb.api import Database
from ncdb.api import FieldCollection
from ncdb_monitor.config import WEBSITE_DATA_FILE

import traceback


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
    
    # Extract nodes from BOTH groups to feed the frontend drop-down matrix
    variables = obsspace.list_variables(group="ObsValue") + obsspace.list_variables(group="ombg")

    for var in variables:
        try:
            field = obsspace.field(var)
            metric = getattr(field, metric_name)
        except Exception as e:
            logger.debug(f"Skipping {obsspace_name}:{var} metric={metric_name} due to {e}")
            continue

        out_file = safe_name(var) + f"_{metric_name}.png"  # Unique suffix prevents overwrites
        plot_path = os.path.join(plot_dir, out_file)
        logger.debug(f"Generating {metric_name} plot {plot_path}")

        try:
            if metric_name == "mean":
                metric.plot(plot_path, band=field.std_dev)
            elif metric_name.startswith("mean") and len(metric_name) > 4:
                # Extract the region name directly (e.g., 'Atlantic' from 'meanAtlantic')
                region_name = metric_name[4:]
                try:
                    # Look up field.std_devAtlantic, field.std_devPacific, etc.
                    std_dev_field = getattr(field, f"std_dev{region_name}")
                    metric.plot(plot_path, band=std_dev_field)
                except Exception:
                    metric.plot(plot_path)
            else:
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
    logger.debug(f"Processing obsspace {obsspace_name}")

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
    variables = obsspace.list_variables(group="ObsValue") + obsspace.list_variables(group="ombg")
    for var in variables:
        logger.debug(f"Processing variable {obsspace_name}:{var}")
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
                variable_info["total_cycles_count"] = len(nobs_cycles)
                
                # Extract the past 4 cycles directly
                recent_cycles = nobs_cycles[-4:]
                recent_vals = []
                recent_times = []  
                for cycle in recent_cycles:
                    try:
                        recent_vals.append(int(nobs_field[cycle].data))
                        recent_times.append({
                            "date": cycle.strftime("%m-%d"),
                            "hour": cycle.strftime("%H")
                        })
                    except Exception:
                        recent_vals.append(0)
                        recent_times.append({"date": "", "hour": "N/A"})
                
                # Pad out leftwards if the tracking history contains less than 4 total cycles
                while len(recent_vals) < 4:
                    recent_vals.insert(0, 0)
                    recent_times.insert(0, {"date": "", "hour": "N/A"})
                    
                variable_info["recent_nobs_values"] = recent_vals
                variable_info["recent_nobs_labels"] = recent_times  
                
                # Maintain the old key as a reference point mapped to the last index of our array
                variable_info["last_nobs_value"] = recent_vals[-1]
                
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

def generate_comparison_plots(db, website_dir, datasets, metric_names):
    """
    Generates comparison plots using FieldCollection across the complete union
    of observation spaces, variables, and cycles to ensure disjoint experiments 
    are plotted safely.
    """
    logger.info("Generating multi-experiment comparison plots")
    comparison_dir = Path(website_dir) / "comparisons"
    comparison_dir.mkdir(exist_ok=True)
    
    comparison_data = []
    
    # 1. UNION OF OBS SPACES
    all_obsspaces = set()
    for dataset in datasets:
        all_obsspaces.update(n.name for n in dataset.obsspaces())
    
    for obs_name in sorted(all_obsspaces):
        obs_safe = safe_name(obs_name)
        obs_comp_dir = comparison_dir / obs_safe
        
        # 2. UNION OF VARIABLES
        all_vars = set()
        active_datasets_for_obs = []
        
        for dataset in datasets:
            try:
                obsspace = dataset.obsspace(obs_name)
                variables = obsspace.list_variables(group="ObsValue") + obsspace.list_variables(group="ombg")
                all_vars.update(variables)
                active_datasets_for_obs.append(dataset)
            except ValueError:
                continue
                
        if not all_vars:
            continue
            
        obs_comp_dir.mkdir(exist_ok=True)
        
        for var in sorted(all_vars):
            # FIX: Include the group prefix (ObsValue vs ombg) in the directory name to prevent overwrites
            var_safe = safe_name(var)
            var_comp_dir = obs_comp_dir / var_safe
            
            var_metrics = {}
            var_dir_created = False
            
            for metric_name in metric_names:
                out_filename = f"{metric_name}.png"
                
                try:
                    collection = FieldCollection()
                    all_cycles = set()
                    
                    # Gather metric fields from the datasets that actually contain this variable
                    for dataset in active_datasets_for_obs:
                        try:
                            obsspace = dataset.obsspace(obs_name)
                            field_root = obsspace.field(var)
                            
                            if hasattr(field_root, metric_name):
                                metric_field = getattr(field_root, metric_name)
                                if metric_field.cycles:
                                    all_cycles.update(metric_field.cycles)
                                    collection.add(metric_field)
                        except ValueError:
                            continue
                    
                    if len(collection._fields) < 2:
                        continue

                    if all_cycles:
                        if not var_dir_created:
                            var_comp_dir.mkdir(exist_ok=True)
                            var_dir_created = True
                            
                        plot_path = var_comp_dir / out_filename
                        logger.info(f"Plotting {obs_name}:{var} ({metric_name})")
                        
                        t1 = min(all_cycles)
                        t2 = max(all_cycles)
                        
                        collection.plot(str(plot_path), t1=t1, t2=t2)
                        
                        relative_path = f"comparisons/{obs_safe}/{var_safe}/{out_filename}"
                        var_metrics[metric_name] = relative_path
                        
                except Exception as e:
                    logger.info(f"Failed plotting {obs_name}:{var} metric={metric_name}: {e}")
                    traceback.print_exc()
                    continue
            
            if var_metrics:
                comparison_data.append({
                    "obsspace": obs_name,
                    "obsspace_safe": obs_safe,
                    "variable": var,
                    "variable_safe": var_safe,
                    "metrics": var_metrics
                })
                
    return comparison_data

def oldgenerate_comparison_plots(db, website_dir, datasets, metric_names):
    """
    Generates comparison plots using FieldCollection across the complete union
    of observation spaces, variables, and cycles to ensure disjoint experiments 
    are plotted safely.
    """
    logger.info("Generating multi-experiment comparison plots")
    comparison_dir = Path(website_dir) / "comparisons"
    comparison_dir.mkdir(exist_ok=True)
    
    comparison_data = []
    
    # 1. UNION OF OBS SPACES: Collect any obs space present in ANY dataset
    all_obsspaces = set()
    for dataset in datasets:
        all_obsspaces.update(n.name for n in dataset.obsspaces())
    
    for obs_name in sorted(all_obsspaces):
        obs_safe = safe_name(obs_name)
        obs_comp_dir = comparison_dir / obs_safe
        
        # 2. UNION OF VARIABLES: Collect any variable available in ANY dataset for this obs space
        all_vars = set()
        active_datasets_for_obs = []
        
        for dataset in datasets:
            try:
                obsspace = dataset.obsspace(obs_name)
                variables = obsspace.list_variables(group="ObsValue") + obsspace.list_variables(group="ombg")
                all_vars.update(variables)
                active_datasets_for_obs.append(dataset)
            except ValueError:
                # This dataset simply doesn't have this observation space, skip it safely
                continue
                
        if not all_vars:
            continue
            
        # Create directories only if we confirm there is data to be plotted
        obs_comp_dir.mkdir(exist_ok=True)
        
        for var in sorted(all_vars):
            var_safe = safe_name(var)
            var_comp_dir = obs_comp_dir / var_safe
            
            var_metrics = {}
            var_dir_created = False
            
            for metric_name in metric_names:
                out_filename = f"{metric_name}.png"
                
                try:
                    collection = FieldCollection()
                    all_cycles = set()
                    has_fields = False
                    
                    # Gather metric fields from the datasets that actually contain this variable
                    for dataset in active_datasets_for_obs:
                        try:
                            obsspace = dataset.obsspace(obs_name)
                            field_root = obsspace.field(var)
                            
                            if hasattr(field_root, metric_name):
                                metric_field = getattr(field_root, metric_name)
                                if metric_field.cycles:
                                    all_cycles.update(metric_field.cycles)
                                    collection.add(metric_field)
                        except ValueError:
                            continue
                    
                    # 3. UNION OF TIMES: If fields exist anywhere, bind them to the global range
                    # dirty:
                    if len(collection._fields) < 2:
                        continue

                    if all_cycles:
                        if not var_dir_created:
                            var_comp_dir.mkdir(exist_ok=True)
                            var_dir_created = True
                            
                        plot_path = var_comp_dir / out_filename
                        logger.info(f"Plotting {obs_name}:{var} ({metric_name})")
                        
                        t1 = min(all_cycles)
                        t2 = max(all_cycles)
                        
                        # Hand off to the expression layer -- your new unique ds_id handles the columns
                        collection.plot(str(plot_path), t1=t1, t2=t2)
                        
                        relative_path = f"comparisons/{obs_safe}/{var_safe}/{out_filename}"
                        var_metrics[metric_name] = relative_path
                        
                except Exception as e:
                    logger.info(f"Failed plotting {obs_name}:{var} metric={metric_name}: {e}")
                    traceback.print_exc()
                    continue
            
            if var_metrics:
                comparison_data.append({
                    "obsspace": obs_name,
                    "obsspace_safe": obs_safe,
                    "variable": var,
                    "variable_safe": var_safe,
                    "metrics": var_metrics
                })
                
    return comparison_data


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
            "has_comparisons": False
        },
        "run": raw_run,
        "datasets": [],
        "comparisons": []
    }

    metric_names = [
        "nobs", 
        "mean",
        "meanAtlantic",
        "meanPacific",
        "meanIndian",
        "meanArctic",
        "meanSouthern"
    ]

    datasets = list(db.datasets())

    for dataset in datasets:
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

    # Trigger comparative generation if 2 or more active experiments exist
    if len(datasets) > 1:
        website_data["comparisons"] = generate_comparison_plots(
            db, website_dir, datasets, metric_names
        )
        website_data["meta"]["has_comparisons"] = True

    website_data_file = os.path.join(website_dir, WEBSITE_DATA_FILE)
    with open(website_data_file, "w") as f:
        json.dump(website_data, f, indent=2)
        
    return website_data
