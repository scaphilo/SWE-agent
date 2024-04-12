from dataclasses import dataclass

from simple_parsing.helpers import FlattenedAccess, FrozenSerializable


@dataclass(frozen=True)
class ActionsArguments(FlattenedAccess, FrozenSerializable):
    """Run real-life actions (opening PRs, etc.) if we can solve the issue."""
    open_pr: bool = False  # Open a PR with the patch if we can solve the issue
    # Skip action if there are already commits claiming to fix the issue. Please only
    # set this to False if you are sure the commits are not fixes or if this is your
    # own repository!
    skip_if_commits_reference_issue: bool = True
    # For PRs: If you want to push the branch to a fork (e.g., because you lack
    # permissions to push to the main repo), set this to the URL of the fork.
    push_gh_repo_url: str = ""

    def __post_init__(self):
        if not self.skip_if_commits_reference_issue and self.push_gh_repo_url:
            raise ValueError(
                "Overriding `skip_if_commits_reference_issue` when you are "
                "pushing to a fork is not supported. You should manually "
                "apply the patch to the forked repository."
            )
