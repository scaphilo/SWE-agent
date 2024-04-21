import json
import re
import logging

from pathlib import Path

from swe_agent import AgentArguments
from swe_agent.swe_agent.model.models import (
    ContextWindowExceededError,
    CostLimitExceededError,
    get_model,
)
from swe_agent.swe_agent.model.model_apistats import APIStats
from swe_agent.swe_agent.prompt_parser.thought_action_prompt_parser import ThoughtActionPromptParser
from swe_agent.swe_agent.prompt_parser.prompt_parser import PromptParserFormatError
from swe_agent.development_environment.utils import LOGGER_NAME
from swe_agent.development_environment.git_communication_interface import GitCommunicationInterface
from swe_agent.development_environment.docker_communication_interface import  DockerCommunicationInterface
from swe_agent.development_environment.development_environment import DevelopmentEnvironment
from tenacity import RetryError
from typing import Optional

logger = logging.getLogger(LOGGER_NAME)


class Agent:
    """Agent handles the behaviour of the large language model
    and how it interacts with the development environment."""

    def __init__(self, name: str, agent_arguments: AgentArguments):
        self.name = name
        self.config = agent_arguments.config
        self.model_commands = self.config._commands + self.config.subroutine_types
        self.model = get_model(model_arguments=agent_arguments.model,
                               commands=self.model_commands)
        self.system_arguments = {
            "command_docs": self.config.command_docs,
            **self.config.env_variables,
        }
        self.agent_setup_arguments = None
        self._parse_command_patterns()
        self.history = []
        self.last_container_id = None

    def setup(self, agent_setup_arguments: dict,
              initial_model_api_statistics: APIStats = None) -> None:
        """Set up the agent for a new instance."""
        self.model.reset_api_statistics(initial_model_api_statistics)
        self.agent_setup_arguments = agent_setup_arguments
        system_message = self.config.system_message_template.format(**self.system_arguments)
        logger.info(f"SYSTEM ({self.name})\n{system_message}")
        self.history = [
            {"role": "system", "content": system_message, "agent": self.name},
        ]
        number_of_demonstrations = len(self.config.demonstrations)
        model_has_function_history_to_message = "history_to_messages" in dir(self.model)
        if number_of_demonstrations > 0 and model_has_function_history_to_message:
            self.append_demonstrations_to_agent_history()

    def append_demonstrations_to_agent_history(self):
        for demonstration_path in self.config.demonstrations:
            if self.config.demonstration_template is None and not self.config.put_demos_in_history:
                raise ValueError(
                    "Cannot use demonstrations without a demonstration template or put_demos_in_history=True")
            # Load history
            logger.info(f"DEMONSTRATION: {demonstration_path}")
            history_entry_list = json.load(open(demonstration_path, "r"))["history"]
            history_entry_list = self.remove_irrelevant_history_entries(history_entry_list)

            if self.config.put_demos_in_history:
                if self.config.demonstration_template is not None:
                    logger.warning("Demonstration template is ignored for put_demos_in_history=True")
                # Add demonstration to history directly as separate messages
                for history_entry in history_entry_list:
                    if history_entry["role"] != "system":
                        history_entry["is_demo"] = True
                        self.history.append(history_entry)
            else:
                # Add demonstration as single message to history
                demo_message = self.model.history_to_messages(history_entry_list, is_demonstration=True, )
                demonstration = self.config.demonstration_template.format(
                    **{"demonstration": demo_message}
                )
                self.history.append({
                    "agent": self.name,
                    "content": demonstration,
                    "is_demo": True,
                    "role": "user",
                })

    def remove_irrelevant_history_entries(self, raw_history_entry_list):
        filtered_history_entry_list = []
        for history_entry in raw_history_entry_list:
            agent_in_history_entry = "agent" in history_entry
            agent_in_history_same_name = history_entry["agent"] == self.name
            if not agent_in_history_entry or (agent_in_history_entry and agent_in_history_same_name):
                filtered_history_entry_list.append(history_entry)
        return filtered_history_entry_list

    @property
    def get_state_command(self) -> str:
        """Return the bash command that will be used to extract the environment state."""
        name_of_state_command = self.config.state_command.name
        return name_of_state_command
    
    def get_overall_history(self) -> list[dict[str, str]]:
        """Return the history of the agent since the last reset."""
        history_entry_list = []
        for history_entry in self.history:
            if history_entry["agent"] == self.name:
                history_entry_list.append(history_entry)
        overall_history = self.config.history_processor(history_entry_list)
        return overall_history

    def save_trajectory(self, trajectory, trajectory_path: Path,
                        env: DevelopmentEnvironment,
                        git_comm_env: GitCommunicationInterface, info):
        log_path = trajectory_path / (git_comm_env.get_repository_details_dict()['instance_id'] + ".traj")
        log_dict = {
            "environment": env.name,
            "trajectory": trajectory,
            "history": self.history,
            "info": info,
        }
        with log_path.open("w") as f:
            json.dump(log_dict, f, indent=2)
        logger.info(f"Saved trajectory to {log_path}")

    def _get_first_match(self, action: str, pattern_type: str) -> Optional[re.Match]:
        """Return the first match of a command pattern in the action string."""
        if pattern_type == "subroutine":
            patterns = {k: v for k, v in self.subroutine_patterns.items()}
        elif pattern_type == "multi_line":
            patterns = {k: v for k, v in self.command_patterns.items() if k in self.config.multi_line_command_endings or k == self.config.submit_command}
            patterns += {k: v for k, v in self.subroutine_patterns.items() if k in self.config.multi_line_command_endings}
        elif pattern_type == "multi_line_no_subroutines":
            patterns = {k: v for k, v in self.command_patterns.items() if k in self.config.multi_line_command_endings}
        else:
            raise ValueError(f"Unknown pattern type: {pattern_type}")
        matches = list()
        for name, pat in patterns.items():
            match = pat.search(action)
            if match:
                matches.append(match)
        if len(matches) == 0:
            return None
        matches = sorted(matches, key=lambda x: x.start())
        return matches[0]

    def _guard_multiline_input(self, action: str) -> str:
        """Split action by multiline commands, then append the first line in each multiline command with "<< '{end_name}'".
        Multiline commands (which are specified by an end_name) are commands that span multiple lines and are terminated by a specific end_name.
        
        Their multi-line argument is sent using a heredoc, which is a way to send a multi-line string to a command in bash.
        """
        parsed_action = list()
        rem_action = action
        while rem_action.strip():
            first_match = self._get_first_match(rem_action, "multi_line_no_subroutines")
            if first_match:
                pre_action = rem_action[:first_match.start()]
                match_action = rem_action[first_match.start():first_match.end()]
                rem_action = rem_action[first_match.end():]
                if pre_action.strip():
                    parsed_action.append(pre_action)
                if match_action.strip():
                    eof = first_match.group(3).strip()
                    if not match_action.split('\n')[0].strip().endswith(f"<< '{eof}'"):
                        guarded_command = match_action[first_match.start():]
                        first_line = guarded_command.split('\n')[0]
                        guarded_command = guarded_command.replace(
                            first_line,
                            first_line + f" << '{eof}'",
                            1
                        )
                        parsed_action.append(guarded_command)
                    else:
                        parsed_action.append(match_action)
            else:
                parsed_action.append(rem_action)
                rem_action = ""
        return '\n'.join(parsed_action)

    def split_actions(self, action: str, pattern_type="subroutine") -> list[dict]:
        """Split an action into a list of actions in a greedy manner,
        each of which is a subroutine call or a single command."""
        parsed_action = list()
        rem_action = action
        while rem_action.strip():
            first_match = self._get_first_match(rem_action, pattern_type)
            if first_match:
                pre_action = rem_action[:first_match.start()]
                match_action = rem_action[first_match.start():first_match.end()]
                rem_action = rem_action[first_match.end():]
                if pre_action.strip():
                    parsed_action.append({'agent': self.name, 'action': pre_action, 'cmd_name': None})
                if match_action.strip():
                    if match_action.split()[0] == self.config.submit_command:
                        parsed_action.append({'agent': self.name,
                                              'action': match_action,
                                              'cmd_name': first_match.group(1)})  # submit command is not a subroutine
                    else:
                        parsed_action.append({'agent': first_match.group(1),
                                              'args': first_match.group(2),
                                              'action': match_action,
                                              'cmd_name': first_match.group(1)})
            else:
                parsed_action.append({'agent': self.name, 'action': rem_action, 'cmd_name': None})
                rem_action = ""
        return parsed_action
    
    def _parse_command_patterns(self):
        self.command_patterns = dict()
        for command in self.config._commands:
            if command.end_name is not None:
                pat = re.compile(fr'^\s*({command.name})\s*(.*?)^({command.end_name})\s*$', re.DOTALL | re.MULTILINE)
                self.command_patterns[command.name] = pat
            else:
                pat = re.compile(fr'^\s*({command.name})\s*(.*?)$', re.MULTILINE)
                self.command_patterns[command.name] = pat
        self.subroutine_patterns = dict()
        for _, subroutine in self.config._subroutines.items():
            if subroutine.end_name is None:
                pat = re.compile(fr'^\s*({subroutine.name})\s*(.*?)$', re.MULTILINE)
                self.subroutine_patterns[subroutine.name,] = pat
            else:
                pat = re.compile(fr'^\s*({subroutine.name})\s*(.*?)^({subroutine.end_name})\s*$', re.DOTALL | re.MULTILINE)
                self.subroutine_patterns[subroutine.name] = pat
        if hasattr(self.config, 'submit_command_end_name'):
            submit_pat = re.compile(rf'^\s*({self.config.submit_command})\s*(.*?)^({self.config.submit_command_end_name})\s*$', re.DOTALL | re.MULTILINE)
        else:
            submit_pat = re.compile(rf'^\s*({self.config.submit_command})(\s*)$', re.MULTILINE)  # group 2 is nothing
        self.subroutine_patterns[self.config.submit_command] = submit_pat
        self.command_patterns[self.config.submit_command] = submit_pat

    def run_model(self,
                  previous_commandline_response: str,
                  container_state: str) -> tuple[str, str, str]:
        model_thought, model_action, model_output = self.run_model_with_error_correction(previous_commandline_response=previous_commandline_response,
                                                                                         container_state=container_state)

        self.history.append(
            {"role": "assistant",
             "content": model_output,
             "thought": model_thought,
             "action": model_action,
             "agent": self.name,
             }
        )

        logger.info(f"💭 THOUGHT ({self.name})\n{model_thought}")
        logger.info(f"🎬 ACTION ({self.name})\n{model_action}")

        return model_thought, model_action, model_output

    def run_model_and_append_to_history(self, observation: str, state: str) -> str:
        """Query the model with the current state and observation with the appropriate template.

        Returns the model output."""

        state_vars = json.loads(state)

        templates = []
        # Determine observation template based on what prior observation was
        if self.history[-1]["role"] == "system" or self.history[-1].get("is_demo", False):
            # Show instance template if prev. obs. was initial system message
            templates = [self.config.instance_template]
            if self.config.strategy_template is not None:
                templates.append(self.config.strategy_template)
        elif observation is None or observation.strip() == "":
            # Show no output template if observation content was empty
            templates = [self.config.next_step_no_output_template]
        else:
            # Show standard output template if there is observation content
            templates = [self.config.next_step_template]

        # Populate selected template(s) with information (e.g., issue, arguments, state)
        messages = []
        for template in templates:
            messages.append(
                template.format(
                    **self.agent_setup_arguments,
                    **self.system_arguments,
                    **state_vars,
                    observation=(observation if observation is not None else ""),
                )
            )

        message = "\n".join(messages)
        logger.info(f"🤖 MODEL INPUT\n{message}")
        self.history.append({"role": "user", "content": message, "agent": self.name})
        model_input = self.get_overall_history()
        model_output = self.model.query(model_input)
        return model_output

    def retry_after_format_fail(self, output):
        """Ask the model to correct (without committing to persistent history) after a malformatted model output"""
        format_error_template = self.config.format_error_template

        logger.warning(f"MALFORMED OUTPUT\n{output}")
        logger.warning(f"FORMAT ERROR\n{format_error_template}")

        temp_history = self.get_overall_history() + [
            {"role": "assistant", "content": output, "agent": self.name},
            {"role": "user", "content": format_error_template, "agent": self.name},
        ]
        return self.model.query(temp_history)

    def retry_after_blocklist_fail(self, output, action):
        """Ask the model to correct (without committing to persistent history) after a disallowed command"""
        name = action.strip().split()[0]
        blocklist_error_message = self.config.blocklist_error_template.format(name=name)

        logger.warning(f"BLOCKLISTED OUTPUT\n{output}")
        logger.warning(f"BLOCKLIST ERROR\n{blocklist_error_message}")

        temp_history = self.get_overall_history() + [
            {"role": "assistant", "content": output, "agent": self.name},
            {"role": "user", "content": blocklist_error_message, "agent": self.name},
        ]
        return self.model.query(temp_history)

    def should_block_action(self, action):
        """Check if the command should be blocked."""
        names = action.strip().split()
        if len(names) == 0:
            return False
        name = names[0]
        if name in self.config.blocklist:
            return True
        if name in self.config.blocklist_standalone and name == action.strip():
            return True
        return False

    def check_format_and_requery(self, model_output: str) -> tuple[str, str, str]:
        """Query the model with the current state and observation with the appropriate template.
        Try to parse the output into a thought and action. Retry if the output is malformatted or the action is blocked.
        Returns the thought, action, and raw model output.
        """
        # Condition for handling outputs with no thought (just action)
        if self.model.model_arguments.model_name == "human":
            return "", model_output, model_output
        elif self.model.model_arguments.model_name == "human_thought":
            model_thought, model_action = ThoughtActionPromptParser()(model_output,
                                                                      self.config._commands + self.config.subroutine_types,
                                                                      strict=False,)
            return model_thought, model_action, model_output

        format_fails = 0
        blocklist_fails = 0

        while format_fails + blocklist_fails <= 2:
            try:
                thought, action = ThoughtActionPromptParser()(model_output,
                                                              self.config._commands + self.config.subroutine_types,
                                                              strict=False, )
            except KeyboardInterrupt:
                raise
            except PromptParserFormatError as e:
                format_fails += 1
                model_output = self.retry_after_format_fail(model_output)
                continue
            if self.should_block_action(action):
                blocklist_fails += 1
                model_output = self.retry_after_blocklist_fail(model_output, action)
            else:
                return thought, action, model_output
        logger.warning(f"Malformat limit reached: \n{model_output}")
        return "Exit due to format error", "exit_format", model_output

    def run_model_with_error_correction(self,
                                        previous_commandline_response: str,
                                        container_state: str) -> tuple[str, str, str]:
        try:
            model_output = self.run_model_and_append_to_history(previous_commandline_response, container_state)
        except KeyboardInterrupt:
            raise
        except RuntimeError as e:
            logger.warning(f"Runtime error: {e}")
            return (
                f"Exit due to runtime error: {e}",
                "exit_error",
                f"exit due to runtime error: {e}",
            )
        except ContextWindowExceededError as e:
            logger.warning(f"Context window exceeded")
            return "Exit due to context window", "exit_context", "Exit due to context window"
        except CostLimitExceededError as e:
            logger.warning(f"Cost limit exceeded")
            return "Exit due to cost limit", "exit_cost", "Exit due to cost limit"
        except RetryError as e:
            logger.warning(f"Retry error: {e}")
            return (
                f"Exit due to retry error: {e}",
                "exit_api",
                f"exit due to retry error: {e}",
            )
        model_thought, model_action, model_output = self.check_format_and_requery(model_output)
        return model_thought, model_action, model_output
    
    def init_environment_vars(self, docker_comm_mgmt: DockerCommunicationInterface):
        self.set_environment_vars(docker_comm_mgmt, self.config.env_variables)

    def set_environment_vars(self, docker_comm_mgmt: DockerCommunicationInterface, env_variables):
        commands_to_execute = (
            [self.config.state_command.code] +
            # [code for code in self.config.util_functions] +
            # [command.code for command in self.config._commands] +
            [f"{k}={v}" for k,v in env_variables.items()]
        )
        commands = "\n".join(commands_to_execute)
        try:
            output, exit_code = docker_comm_mgmt.communicate(commands)
            if exit_code != 0:
                raise RuntimeError(f"Nonzero return code: {docker_comm_mgmt.return_code}\nOutput: {output}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning("Failed to set environment variables")
            raise e
        command_files = list()
        for file in self.config.command_files:
            command_file = dict()
            contents = open(file, 'r').read()
            command_file['contents'] = contents
            filename = Path(file).name
            if not contents.strip().startswith('#!'):
                if filename.endswith('.sh'):
                    # files are sourced, so they are not executable
                    command_file['name'] = Path(file).name
                    command_file['type'] = 'source_file'
                elif filename.startswith('_'):
                    # files are sourced, so they are not executable
                    command_file['name'] = Path(file).name
                    command_file['type'] = 'utility'
                else:
                    raise ValueError((
                        f"Non-shell script file {file} does not start with shebang.\n"
                        "Either add a shebang (#!) or change the file extension to .sh if you want to source it.\n"
                        "You can override this behavior by adding an underscore to the file name (e.g. _utils.py)."
                    ))
            else:
                # scripts are made executable
                command_file['name'] = Path(file).name.rsplit('.', 1)[0]
                command_file['type'] = 'script'
            command_files.append(command_file)
        docker_comm_mgmt.add_commands(command_files)
    
    def get_environment_vars(self, env):
        env_vars = dict()
        for var in self.config.env_variables:
            env_vars[var] = env.communicate(f"echo ${var}").strip()
        return env_vars
    
    def call_subroutine(self, agent_name, sub_action, env):
        env_vars = self.get_environment_vars(env)
        cwd = env.communicate("pwd -P").strip()
        init_observation = self.config._subroutines[agent_name].init_observation
        if init_observation is not None:
            obs, _, _, _ = env.step(init_observation.format(args=sub_action['args']))
        else:
            obs = None
        if env.return_code != 0:
            self.history.append({"role": "user", "content": obs, "agent": agent_name})
            raise RuntimeError(f"Nonzero return code: {env.return_code} for init_observation in {agent_name}.\n{obs}")
        return_type = self.config._subroutines[agent_name].return_type
        sub_agent = Agent(agent_name, self.config._subroutines[agent_name].agent_args)
        sub_agent_output = sub_agent.run(
            {"issue": sub_action['args']},
            env,
            previous_commandline_response=obs,
            return_type=return_type,
            init_model_stats=self.model.api_statistics,)
        self.history += sub_agent.history
        self.set_environment_vars(env, env_vars)
        env.communicate(f"cd {cwd}")
        self.model.api_statistics.replace(sub_agent.model.api_statistics)
        return sub_agent_output

    def run(self,
            agent_setup_arguments: dict,
            development_environment: DevelopmentEnvironment,
            previous_commandline_response: str = None,
            trajectory_path: Optional[Path] = None,
            return_type: Optional[str] = "info",
            init_model_stats: Optional[APIStats] = None,):
        """
        Run the agent on an environment.
        Return the final value of the specified return type.
        """
        done = False
        docker_communication_interface = development_environment.get_docker_communication_interface()
        git_communication_interface = development_environment.get_git_communication_interface()
        if docker_communication_interface.get_container_obj().id != self.last_container_id:
            logger.info(f"Initializing agent settings for container {docker_communication_interface.get_container_obj().id}")
            self.init_environment_vars(docker_communication_interface)
            self.last_container_id = docker_communication_interface.container_obj.id
        # Re-initialize primary
        self.setup(agent_setup_arguments=agent_setup_arguments,
                   initial_model_api_statistics=init_model_stats)

        # Run action/observation loop
        trajectory = []
        agent_infos = {}
        while not done:
            container_state, exit_code = docker_communication_interface.communicate(bash_command=self.get_state_command)
            model_thought, model_action, model_output = self.run_model(previous_commandline_response=previous_commandline_response,
                                                                       container_state=container_state)
            new_commandline_response_list = list()
            run_action = self._guard_multiline_input(model_action)
            for sub_action in self.split_actions(run_action):
                if sub_action['agent'] == self.name or sub_action['cmd_name'] == self.config.submit_command:
                    new_commandline_response_element, _, done, agent_infos = development_environment.step(sub_action['action'])
                    new_commandline_response_list.append(new_commandline_response_element)
                    if sub_action['cmd_name'] == self.config.submit_command:
                        done = True
                    if done:
                        break
                else:
                    agent_name = sub_action['agent']
                    sub_agent_output = self.call_subroutine(agent_name, sub_action, docker_communication_interface)
                    new_commandline_response_list.append(sub_agent_output)

            new_commandline_response = ""
            for commandline_response_element in new_commandline_response_list:
                if commandline_response_element is not None:
                    new_commandline_response = new_commandline_response + "\n" + commandline_response_element

            trajectory.append(
                {
                    "action": model_action,
                    "observation": new_commandline_response,
                    "response": model_output,
                    "state": container_state,
                    "thought": model_thought,
                }
            )
            agent_infos['model_api_statistics'] = self.model.api_statistics.to_dict()
            if trajectory_path:
                self.save_trajectory(trajectory=trajectory,
                                     trajectory_path=trajectory_path,
                                     env=development_environment,
                                     git_comm_env=git_communication_interface,
                                     info=agent_infos)

            previous_commandline_response = new_commandline_response  # Prepare next loop for agent
        if return_type == "info":
            return agent_infos
        if return_type == "info_trajectory":
            return agent_infos, trajectory
        if return_type != "info":
            return trajectory[-1][return_type]
