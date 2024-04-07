from dataclasses import dataclass
from typing import Optional, Any, Tuple

from simple_parsing import field
from simple_parsing.helpers import FrozenSerializable

from swe_agent import AgentArguments
from swe_agent.swe_agent.agent.agent_subroutine import AgentSubroutine
from swe_agent.swe_agent.command.commands import Command
from swe_agent.swe_agent.command.command_parser import CommandParser
from swe_agent.swe_agent.processor.history_processor import HistoryProcessor
from swe_agent.swe_agent.parsing import ParseFunction


@dataclass(frozen=True)
class AgentConfig(FrozenSerializable):
    system_template: str
    instance_template: str
    next_step_template: Optional[str] = None  # defaults to instance_template
    next_step_no_output_template: Optional[str] = None  # defaults to next_step_template
    strategy_template: Optional[str] = None
    demonstration_template: Optional[str] = None
    demonstrations: list[str] = field(default_factory=list)
    put_demos_in_history: bool = False  # if True, add demonstration to history instead of as a single message
    format_error_template: str = None # defaults to format_error_template in ParseFunction
    command_files: list[str] = field(default_factory=list)
    env_variables: dict[str, str] = field(default_factory=dict)
    util_functions: list[str] = field(default_factory=list)
    submit_command: str = "submit"
    parse_function: str = "ThoughtActionParser"
    parse_command: str = "ParseCommandBash"
    history_processor: str = "DefaultHistoryProcessor"
    history_processor_args: dict[str, Any] = field(default_factory=dict)
    command_docs: str = None
    blocklist_error_template: str = "Interactive operation '{name}' is not supported by this environment"
    blocklist: Tuple[str] = (
        "vim",
        "vi",
        "emacs",
        "nano",
        "nohup",
        "git",
    )
    blocklist_standalone: Tuple[str] = (
        "python",
        "python3",
        "ipython",
        "bash",
        "sh",
        "exit",
        "/bin/bash",
        "/bin/sh",
        "nohup",
        "vi",
        "vim",
        "emacs",
        "nano",
    )
    # Should extract environment state in a json readable form
    state_command: Command = Command(
        name="state",
        code="""state() {
            echo '{"working_dir": "'$(realpath --relative-to=$ROOT/.. $PWD)'"}';
        };""",
    )
    _commands: list[Command] = field(default_factory=list)
    _subroutines: dict[str, AgentSubroutine] = field(default_factory=dict)
    subroutine_types: list[AgentSubroutine] = field(default_factory=list)

    def __post_init__(self):
        if self.next_step_template is None:
            object.__setattr__(self, "next_step_template", self.instance_template)
        if self.next_step_no_output_template is None:
            object.__setattr__(
                self, "next_step_no_output_template", self.next_step_template
            )

        object.__setattr__(self, "parse_command", CommandParser.get(self.parse_command))
        for file in self.command_files:
            commands = self.parse_command.parse_command_file(file)

            util_functions = [
                command for command in commands if command.name.startswith("_")
            ]
            commands = [
                command for command in commands if not command.name.startswith("_")
            ]

            object.__setattr__(
                self, "util_functions", self.util_functions + util_functions
            )
            object.__setattr__(self, "_commands", self._commands + commands)

        for subroutine in self.subroutine_types:
            if subroutine.name == 'submit':
                raise ValueError("Cannot use 'submit' as a subroutine name")
            agent_args = AgentArguments(
                model=subroutine.model,
                config_file=subroutine.agent_file,
                )
            object.__setattr__(subroutine, "agent_args", agent_args)
            object.__setattr__(self, "_subroutines", {**self._subroutines, subroutine.name: subroutine})

        multi_line_command_endings = {
            command.name: command.end_name
            for command in [*self._commands, *self._subroutines.values()]
            if command.end_name is not None
        }
        object.__setattr__(self, "multi_line_command_endings", multi_line_command_endings)
        object.__setattr__(
            self,
            "command_docs",
            self.parse_command.generate_command_docs(
                self._commands,
                self.subroutine_types,
                **self.env_variables,
                ),
            )
        object.__setattr__(self, "parse_function", ParseFunction.get(self.parse_function))
        if self.format_error_template is None:
            object.__setattr__(
                self,
                "format_error_template",
                self.parse_function.format_error_template,
                )
        object.__setattr__(self, "format_error_template", self.format_error_template.format(**self.__dict__))
        for command in self._commands:
            if command.name == self.submit_command:
                object.__setattr__(self, "submit_command_end_name", command.end_name)
                break
        object.__setattr__(
            self, "history_processor",
            HistoryProcessor.get(self.history_processor, **self.history_processor_args)
            )
