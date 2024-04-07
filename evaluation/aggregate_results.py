import argparse
import numpy as np
import pandas as pd
from result_aggregator import ResultAggregator
from rich import print


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate results from experiments")
    parser.add_argument("--folder", type=str, help="Folder containing experiment results", default="../trajectories")
    parser.add_argument("--model", nargs='+', type=str, help="Model(s) to filter results by.")
    parser.add_argument("--dataset", nargs='+', type=str, help="Dataset to filter results by.")
    parser.add_argument("--setup", nargs='+', type=str, help="Setup to filter results by.")
    parser.add_argument("--runs_min", type=int, help="Minimum number of runs that experiment should have been run for.")
    parser.add_argument("--runs_max", type=int, help="Maximum number of runs taken into account")
    args = parser.parse_args()

    result_aggregator = ResultAggregator(args.folder, args.runs_max)
    df = result_aggregator.get_results_df()

    grouped_data = (
        df.groupby(ResultAggregator.COLUMNS[:7])
        .agg(
            {
                "Run": "count",  # Count the number of runs
                "Not Generated": "mean",
                "Generated": "mean",
                "Applied": "mean",
                "Resolved": "mean",
                "Resolved IDs": lambda x: len(set([item for sublist in x for item in sublist])),
                "Costs Success": lambda x: np.mean([item for sublist in x for item in sublist]),
                "Costs Failure": lambda x: np.mean([item for sublist in x for item in sublist]),
                "Costs Overall": lambda x: np.mean([item for sublist in x for item in sublist]),
            }
        )
        .round(2)
        .reset_index()
        .rename(columns={"Resolved IDs": "Pass@K", "Run": "Runs"})
    )

    # Filtering
    if args.model:
        grouped_data = grouped_data[grouped_data['Model'].isin(args.model)]
    if args.dataset:
        grouped_data = grouped_data[grouped_data['Dataset'].isin(args.dataset)]
    if args.setup:
        grouped_data = grouped_data[grouped_data['Setup'].isin(args.setup)]
    if args.runs_min:
        grouped_data = grouped_data[grouped_data['Run'] >= args.runs_min]

    print(f"Total experiments run: {grouped_data.shape[0]}")
    grouped_data_sorted = grouped_data.sort_values(by=['Dataset', 'Resolved'], ascending=[True, False])
    pd.set_option("display.max_rows", None)
    grouped = grouped_data_sorted.groupby('Dataset')

    for name, group in grouped:
        print(f'\n-----------------\nDataset: {name}\n-----------------')
        print(group.to_string(index=False))
