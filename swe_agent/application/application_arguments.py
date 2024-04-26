from dataclasses import dataclass
from pathlib import Path

from simple_parsing.helpers import FlattenedAccess, FrozenSerializable

from swe_agent import DevelopmentEnvironmentArguments, AgentArguments
from swe_agent.application.action_arguments import ActionsArguments
from swe_agent.development_environment.git_communication_interface import GITHUB_ISSUE_URL_PATTERN


@dataclass(frozen=True)
class ApplicationArguments(FlattenedAccess, FrozenSerializable):
    development_environment_arguments: DevelopmentEnvironmentArguments
    agent: 'AgentArguments'
    actions: ActionsArguments
    instance_filter: str = ".*"  # Only run instances that completely match this regex
    skip_existing: bool = True  # Skip instances with existing trajectories
    suffix: str = ""

    @property
    def run_name(self):
        """Generate a unique name for this run based on the arguments."""
        model_name = self.agent.model.model_name.replace(":", "-")
        data_stem = get_data_path_name(self.development_environment_arguments.sourcecode_repository_path)
        config_stem = Path(self.agent.config_file).stem

        temp = self.agent.model.temperature
        top_p = self.agent.model.top_p

        per_instance_cost_limit = self.agent.model.per_instance_cost_limit
        install_environment = self.development_environment_arguments.install_environment

        return (
            f"{model_name}__{data_stem}__{config_stem}__t-{temp:.2f}__p-{top_p:.2f}"
            + f"__c-{per_instance_cost_limit:.2f}__install-{int(install_environment)}"
            + (f"__{self.suffix}" if self.suffix else "")
        )


def get_data_path_name(data_path: str):
    # if data_path is a file, return the file stem
    # elif it's a github url, return the owner__repo_name
    match = GITHUB_ISSUE_URL_PATTERN.search(data_path)
    if match:
        owner, repo, issue_number = match.groups()
        return f"{owner}__{repo}"
    return Path(data_path).stem
