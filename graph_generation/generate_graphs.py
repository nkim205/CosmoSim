import argparse
import contextlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import List, TextIO

import exputil
import networkx as nx
from astropy import units as u

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from graph_generation.helpers.graph_tools import *  # noqa: E402,F401,F403
from utils.cells import read_cells, read_cells_starlink  # noqa: E402
from utils.distance_tools import (  # noqa: E402
    distance_m_between_satellites,
    distance_m_ground_station_to_cell,
    distance_m_ground_station_to_satellite,
    geodetic2cartesian,
)
from utils.ground_stations import read_ground_stations_basic  # noqa: E402
from utils.isls import read_isls  # noqa: E402
from utils.tles import read_tles  # noqa: E402
import utils.global_variables as global_vars  # noqa: E402

PROJECT_ROOT = BASE_DIR
GRAPHS_DIR = (BASE_DIR / "graph_generation" / "graphs").resolve()
INPUTS_DIR = BASE_DIR / "inputs"
GROUNDSTATIONS_DIR = INPUTS_DIR / "groundstations"
CELLS_DIR = INPUTS_DIR / "cells"
CONSTELLATION_OUTPUT_DIR_CANDIDATES: List[Path] = [
    (BASE_DIR / "constellation_configs" / "gen_data").resolve(),
    (BASE_DIR / "constellation_configurations" / "gen_data").resolve(),
    (BASE_DIR / "constellation_configurations" / "configs").resolve(),
]

DEFAULT_UPDATE_INTERVAL_MS = 1000
DEFAULT_DURATION_S = 15


class _StreamTee:
    def __init__(self, primary: TextIO, secondary: TextIO):
        self.primary = primary
        self.secondary = secondary

    def write(self, data: str) -> None:
        self.primary.write(data)
        self.secondary.write(data)

    def flush(self) -> None:
        self.primary.flush()
        self.secondary.flush()


@contextlib.contextmanager
def tee_output(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = _StreamTee(original_stdout, log_file)
        sys.stderr = _StreamTee(original_stderr, log_file)
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


def resolve_constellation_dir(constellation_id: str) -> Path:
    candidate = Path(constellation_id)
    if candidate.is_absolute():
        if candidate.is_dir():
            return candidate.resolve()
        raise FileNotFoundError(f"Constellation output not found at absolute path '{candidate}'.")

    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()

    project_candidate = (PROJECT_ROOT / candidate).resolve()
    if project_candidate.exists() and project_candidate.is_dir():
        return project_candidate

    for root in CONSTELLATION_OUTPUT_DIR_CANDIDATES:
        if not root.exists():
            continue
        rooted = root / constellation_id
        if rooted.exists() and rooted.is_dir():
            return rooted
    raise FileNotFoundError(
        f"Constellation output not found for '{constellation_id}'. "
        "Generate configurations first (expected under constellation_configs/gen_data "
        "or constellation_configurations/{gen_data,configs})."
    )


def compute_graph_subdir(constellation_config: str) -> str:
    name = Path(constellation_config).name
    parts = name.split("_")
    if len(parts) > 2:
        prefix = parts[:-2]
        if prefix:
            return "_".join(prefix)
    return name


def prepare_output_dir(graphs_dir: Path, constellation_config: str) -> Path:
    subdir = compute_graph_subdir(constellation_config)
    base_output = graphs_dir / subdir
    base_output.mkdir(parents=True, exist_ok=True)
    return base_output


def resolve_starlink_cells_path() -> Path:
    inputs_starlink = CELLS_DIR / "starlink_cells.txt"
    if inputs_starlink.exists():
        return inputs_starlink
    raise FileNotFoundError(
        "Starlink cell population file not found under inputs/cells/starlink_cells.txt."
    )


def load_ground_stations(groundstations_file: Path):
    basics = read_ground_stations_basic(str(groundstations_file))
    extended = []
    for entry in basics:
        cartesian = geodetic2cartesian(
            float(entry["latitude_degrees_str"]),
            float(entry["longitude_degrees_str"]),
            entry["elevation_m_float"],
        )
        extended.append(
            {
                "gid": entry["gid"],
                "name": entry["name"],
                "latitude_degrees_str": entry["latitude_degrees_str"],
                "longitude_degrees_str": entry["longitude_degrees_str"],
                "elevation_m_float": entry["elevation_m_float"],
                "cartesian_x": cartesian[0],
                "cartesian_y": cartesian[1],
                "cartesian_z": cartesian[2],
            }
        )
    return extended


def ensure_simple_name(label: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} name must be non-empty.")
    if Path(value).name != value or any(sep in value for sep in ("/", "\\")):
        raise ValueError(f"{label} name '{value}' must not contain path separators.")
    return value


def resolve_groundstations_catalog(name: str) -> Path:
    candidates = [
        GROUNDSTATIONS_DIR / name,
        GROUNDSTATIONS_DIR / f"{name}.txt",
        GROUNDSTATIONS_DIR / f"{name}.csv",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Ground station catalogue '{name}' not found under {GROUNDSTATIONS_DIR} "
        "(expected files like <name>.txt)."
    )


def resolve_cells_for_country(country: str) -> Path:
    candidate = CELLS_DIR / f"{country}.txt"
    if candidate.exists() and candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Cell allocation for '{country}' not found at {candidate}. "
        "Place the file under inputs/cells/<country>.txt."
    )


def generate_satellite_shell_index(num_satellites, num_orbits, num_sats_per_orbit):
    satellites_shell_idx = {}
    current_sat_id = 0
    
    for shell_idx, (orbits, sats_per_orbit) in enumerate(zip(num_orbits, num_sats_per_orbit)):
        shell_size = orbits * sats_per_orbit
        for sat_id in range(current_sat_id, min(current_sat_id + shell_size, num_satellites)):
            satellites_shell_idx[sat_id] = shell_idx
        current_sat_id += shell_size

    return satellites_shell_idx


def generate_all_graphs(
    graph_path: Path,
    constellation_dir: Path,
    constellation_config: str,
    country: str,
    groundstations_file: Path,
    cells_file: Path,
    dynamic_state_update_interval_ms: int,
    simulation_start_time_s: int,
    simulation_end_time_s: int,
    include_global_cells: bool = True,
):
    print(
        f"Generating graphs for '{constellation_config}' ({country}) "
        f"from t={simulation_start_time_s}s to t={simulation_end_time_s}s "
        f"every {dynamic_state_update_interval_ms}ms"
    )

    graph_path.mkdir(parents=True, exist_ok=True)
    country_graph_path = graph_path / country
    country_graph_path.mkdir(parents=True, exist_ok=True)

    isls_path = constellation_dir / "isls.txt"
    tles_path = constellation_dir / "tles.txt"
    description_path = constellation_dir / "description.txt"
    for path, label in [
        (isls_path, "ISL list"),
        (tles_path, "TLE file"),
        (description_path, "description file"),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"Required {label} missing at {path}.")

    starlink_cells_path = resolve_starlink_cells_path()

    ground_stations = load_ground_stations(groundstations_file)
    tles = read_tles(str(tles_path))
    satellites = tles["satellites"]
    list_isls = read_isls(str(isls_path), len(satellites))
    epoch = tles["epoch"]
    cells = read_cells(str(cells_file))
    # Global res-3 cells are only consumed by generate_capacities_competing_traffic.py.
    starlink_cells = read_cells_starlink(str(starlink_cells_path)) if include_global_cells else []
    description = exputil.PropertiesConfig(str(description_path))

    simulation_start_time_ns = simulation_start_time_s * 1_000_000_000
    simulation_end_time_ns = simulation_end_time_s * 1_000_000_000
    dynamic_state_update_interval_ns = dynamic_state_update_interval_ms * 1_000_000

    n_shells = exputil.parse_positive_int(description.get_property_or_fail("num_shells"))
    if n_shells == 1:
        max_gsl_length_m = exputil.parse_positive_float(
            description.get_property_or_fail("max_gsl_length_m")
        )
        max_isl_length_m = exputil.parse_positive_float(
            description.get_property_or_fail("max_isl_length_m")
        )
    else:
        num_orbits = json.loads(description.get_property_or_fail("num_orbits"))
        num_sats_per_orbit = json.loads(description.get_property_or_fail("num_sats_per_orbit"))
        max_gsl_length_m = json.loads(description.get_property_or_fail("max_gsl_length_m"))
        max_isl_length_m = json.loads(description.get_property_or_fail("max_isl_length_m"))
        satellites_shell_idx = generate_satellite_shell_index(
            len(satellites), num_orbits, num_sats_per_orbit
        )
        print(
            f"Constellation shells: num_orbits={num_orbits}, "
            f"num_sats_per_orbit={num_sats_per_orbit}"
        )

    for t in range(
        simulation_start_time_ns, simulation_end_time_ns, dynamic_state_update_interval_ns
    ):
        graph_path_filename = country_graph_path / f"graph_{t}.txt"
        time_point = epoch + t * u.ns

        graph = nx.DiGraph()
        sat_capacity = [0] * len(satellites)

        for ground_station in ground_stations:
            for sid in range(len(satellites)):
                if n_shells == 1:
                    max_length = max_gsl_length_m
                else:
                    max_length = max_gsl_length_m[satellites_shell_idx[sid]]

                distance_m = distance_m_ground_station_to_satellite(
                    ground_station, satellites[sid], str(epoch), str(time_point)
                )
                if distance_m <= max_length:
                    graph.add_edge(
                        len(satellites) + ground_station["gid"],
                        sid,
                        weight=round(distance_m),
                        capacity=0,
                    )

        for (a, b) in list_isls:
            if n_shells == 1:
                max_length = max_isl_length_m
            else:
                max_length = max_isl_length_m[satellites_shell_idx[a]]

            sat_distance_m = distance_m_between_satellites(
                satellites[a], satellites[b], str(epoch), str(time_point)
            )
            if sat_distance_m <= max_length:
                graph.add_edge(a, b, weight=round(sat_distance_m), capacity=global_vars.isl_capacity)
                graph.add_edge(b, a, weight=round(sat_distance_m), capacity=global_vars.isl_capacity)

                sat_capacity[a] += global_vars.isl_capacity
                sat_capacity[b] += global_vars.isl_capacity

        for cell in cells:
            cell_id = cell["cell"]
            for sid in range(len(satellites)):
                if n_shells == 1:
                    max_length = max_gsl_length_m
                else:
                    max_length = max_gsl_length_m[satellites_shell_idx[sid]]

                distance_m = distance_m_ground_station_to_cell(
                    cell_id, satellites[sid], str(epoch), str(time_point)
                )
                if distance_m < max_length:
                    graph.add_edge(
                        sid, cell_id, weight=round(distance_m), capacity=global_vars.ku_beam_capacity
                    )

        for cell in starlink_cells:
            cell_id = cell["cell"]
            for sid in range(len(satellites)):
                if n_shells == 1:
                    max_length = max_gsl_length_m
                else:
                    max_length = max_gsl_length_m[satellites_shell_idx[sid]]

                distance_m = distance_m_ground_station_to_cell(
                    cell_id, satellites[sid], str(epoch), str(time_point)
                )
                if distance_m < max_length:
                    graph.add_edge(
                        sid, cell_id, weight=round(distance_m), capacity=global_vars.ku_beam_capacity
                    )

        with open(graph_path_filename, "wb") as f:
            pickle.dump(graph, f)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate graph snapshots for a single constellation-country pair.\n"
            "Provide the constellation config name, ground station catalogue name, "
            "and country (the cells file is inferred from inputs/cells/<country>.txt)."
        )
    )
    parser.add_argument(
        "--constellation-config",
        "-c",
        required=True,
        help="Constellation configuration name (e.g., starlink_all).",
    )
    parser.add_argument(
        "--groundstations",
        "-g",
        required=True,
        help="Ground station catalogue name (e.g., ground_stations_starlink).",
    )
    parser.add_argument(
        "--country",
        "-n",
        required=True,
        help="Country name (cells are read from inputs/cells/<country>.txt).",
    )
    parser.add_argument(
        "--graphs-dir",
        type=Path,
        default=GRAPHS_DIR,
        help=f"Root directory for graph outputs (default: {GRAPHS_DIR}).",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Simulation start time in seconds (default: 0).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_S,
        help=f"Total duration in seconds to generate (default: {DEFAULT_DURATION_S}).",
    )
    parser.add_argument(
        "--constellation-root",
        dest="constellation_roots",
        action="append",
        default=[],
        type=Path,
        help="Additional directory to search for constellation outputs (may be repeated).",
    )
    parser.add_argument(
        "--skip-global-cells",
        action="store_true",
        help=(
            "Omit sat->cell edges for inputs/cells/starlink_cells.txt (global res-3 cells). "
            "Only the competing-traffic workflow reads them; write such graphs to a separate --graphs-dir."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned generation info without creating graphs.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Optional log file to capture stdout/stderr for this run.",
    )
    return parser


def parse_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be a positive integer.")

    try:
        args.constellation_config = ensure_simple_name("constellation", args.constellation_config)
        args.groundstations = ensure_simple_name("groundstations", args.groundstations)
        args.country = ensure_simple_name("country", args.country)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        args.groundstations = resolve_groundstations_catalog(args.groundstations)
    except FileNotFoundError as exc:
        parser.error(str(exc))

    try:
        args.cells = resolve_cells_for_country(args.country)
    except FileNotFoundError as exc:
        parser.error(str(exc))

    constellation_roots: List[Path] = []
    for root in args.constellation_roots:
        resolved = root.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            parser.error(f"Constellation root '{root}' does not exist or is not a directory.")
        constellation_roots.append(resolved)
    args.constellation_roots = constellation_roots
    if args.log_file is not None:
        args.log_file = args.log_file.expanduser().resolve()

    return args


def main() -> None:
    parser = build_parser()
    args = parse_args(parser)

    log_context: contextlib.AbstractContextManager[None]
    if args.log_file:
        log_context = tee_output(args.log_file)
    else:
        log_context = contextlib.nullcontext()

    with log_context:
        for extra_root in args.constellation_roots:
            if extra_root not in CONSTELLATION_OUTPUT_DIR_CANDIDATES:
                CONSTELLATION_OUTPUT_DIR_CANDIDATES.append(extra_root)

        constellation_dir = resolve_constellation_dir(args.constellation_config)
        graphs_root = args.graphs_dir.expanduser().resolve()
        update_interval_ms = DEFAULT_UPDATE_INTERVAL_MS
        output_dir = prepare_output_dir(graphs_root, args.constellation_config)

        if args.dry_run:
            print(
                f"[dry-run] would generate graphs in {output_dir} using:\n"
                f"  constellation dir: {constellation_dir}\n"
                f"  groundstations: {args.groundstations}\n"
                f"  cells: {args.cells}\n"
                f"  country label: {args.country}\n"
                f"  start: {args.start}s duration: {args.duration}s "
                f"(update every {update_interval_ms}ms)"
            )
            return

        simulation_start = args.start
        simulation_end = args.start + args.duration

        start_time = time.time()
        generate_all_graphs(
            output_dir,
            constellation_dir,
            args.constellation_config,
            args.country,
            args.groundstations,
            args.cells,
            update_interval_ms,
            simulation_start,
            simulation_end,
            include_global_cells=not args.skip_global_cells,
        )
        elapsed = time.time() - start_time
        print(f"Finished generating graphs in {output_dir} (elapsed {elapsed:.1f}s).")


if __name__ == "__main__":
    main()
