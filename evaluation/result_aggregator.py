import glob
import json
import os
import pandas as pd
import warnings
from pathlib import Path
from rich import print

warnings.filterwarnings("ignore")


class ResultAggregator:

    COLUMNS = [
        "Model",
        "Dataset",
        "Setup",
        "Temp.",
        "Top P",
        "Cost",
        "Install",
        "Run",
        "Not Generated",
        "Generated",
        "Applied",
        "Resolved",
        "Resolved IDs",
        "Costs Success",
        "Costs Failure",
        "Costs Overall",
    ]

    def __init__(self, folder_name, max_runs):
        self.results = []
        self.folder_name = folder_name
        self.parsed_folder = ""
        self.max_runs = max_runs

    def get_folders(self):
        return [entry for entry in Path(self.folder_name).iterdir() if entry.is_dir()]

    def parse_folder_name(self):
        """
        Parse the folder name to get the different parts
        """
        self.parsed_folder = self.folder_name.split("__")
        if len(self.parsed_folder) == 7:
            self.parsed_folder.append("")
        return self.parsed_folder

    def convert_experiments_to_rows(self):
        """
        Convert each experiment to a row in the csv
        """
        rows = []
        directories = self.get_folders()
        for directory in directories:
            folders = self.get_folders(directory)
            for folder in folders:
                # Skip debug folders
                if "debug" in folder.name:
                    continue

                # Skip fine tuned models
                if "ft_gpt-3.5" in folder.name:
                    continue

                # Skip folders without a results.json file
                json_file = folder / "results.json"
                if not json_file.exists():
                    # print(f"No json file in {folder}")
                    continue

                # Extract run attributes
                folder_data = self.parse_folder_name(folder.name)
                model = folder_data[0]
                dataset = folder_data[1]
                if dataset.startswith("swe-bench-dev-easy-"):
                    dataset = dataset[len("swe-bench-dev-easy-"):]
                elif dataset.startswith("swe-bench-dev-"):
                    dataset = dataset[len("swe-bench-dev-"):]
                setup = folder_data[2]
                if len(folder_data) != 8:
                    # TODO: This might be too strict?
                    continue
                temperature = float(folder_data[3][len("t-"):].strip())
                top_p = float(folder_data[4][len("p-"):].strip())
                cost = float(folder_data[5][len("c-"):].strip())
                install = "Y" if folder_data[6].strip() == "install-1" else "N"

                # Parse out run number
                run = folder_data[-1]
                if "run" not in run:
                    continue

                try:
                    if "run-" in run:
                        run = int(run.split("run-")[-1].split("-")[0].replace("_", "").strip())
                    else:
                        run = int(run.split("run")[-1].split("-")[0].replace("_", "").strip())
                except Exception as e:
                    print(run)
                    raise e

                if self.max_runs is not None and run > self.max_runs:
                    continue

                # Load results.json file
                with json_file.open() as file:
                    results_data = json.load(file)
                report = results_data.get("report", {})

                # Extract resolved ids (to calculate pass@k)
                resolved_ids = []
                if "resolved" in results_data and isinstance(results_data["resolved"], list):
                    resolved_ids = results_data["resolved"]
                elif "counts" in results_data and isinstance(results_data["counts"]["resolved"], list):
                    resolved_ids = results_data["counts"]["resolved"]

                # Extract instance costs from trajectories
                costs_overall = []
                costs_success = []
                costs_failure = []
                for x in glob.glob(os.path.join(str(folder), "*.traj")):
                    traj_data = json.load(open(x))
                    if "model_stats" not in traj_data["info"]:
                        continue
                    run_cost = traj_data["info"]["model_stats"]["instance_cost"]
                    inst_id = x.split("/")[-1].split(".")[0]
                    costs_overall.append(run_cost)
                    if inst_id in resolved_ids:
                        costs_success.append(run_cost)
                    else:
                        costs_failure.append(run_cost)

                # Create run row, write to csv
                rows.append(
                    [
                        model,
                        dataset,
                        setup,
                        temperature,
                        top_p,
                        cost,
                        install,
                        run,
                        report.get("# Not Generated", 0),
                        report.get("# Generated", 0),
                        report.get("# Applied", 0),
                        report.get("# Resolved", 0),
                        resolved_ids,
                        costs_success,
                        costs_failure,
                        costs_overall,
                    ]
                )

        return rows

    def get_results_df(self):
        rows = self.convert_experiments_to_rows()
        return (
            pd.DataFrame(rows, columns=self.COLUMNS)
            .sort_values(by=self.COLUMNS[:8])
        )

    def get_results_csv(self):
        self.get_results_df().to_csv("results.csv")
        print("Experiment results written to results.csv")
