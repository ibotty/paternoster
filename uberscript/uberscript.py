import argparse
import sys
import os
import os.path
import json
from collections import namedtuple

from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.inventory import Inventory
from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.plugins.callback import CallbackBase

Options = namedtuple('Options', ['connection', 'module_path', 'forks', 'become', 'become_method', 'become_user', 'check', 'listhosts', 'listtasks', 'listtags', 'syntax'])


class UberScript:

  def __init__(self, playbook, parameters):
    self.playbook = playbook
    self.parameters = parameters
  
  def _find_param(self, fname):
    for name, short, param in self.parameters:
      if name == fname or short == fname:
        return (name, short, param)
  
  def _build_argparser(self):
    parser = argparse.ArgumentParser(add_help=False)
    requiredArgs = parser.add_argument_group('required arguments')
    optionalArgs = parser.add_argument_group('optional arguments')

    optionalArgs.add_argument(
      '-h', '--help', action='help', default=argparse.SUPPRESS,
      help='show this help message and exit'
    )

    for name, short, param in self.parameters:
      argParams = param.copy()
      argParams.pop('depends', None)
      
      if param.get('required', False):
        requiredArgs.add_argument('-' + short, '--' + name, **argParams)
      else:
        optionalArgs.add_argument('-' + short, '--' + name, **argParams)

    return parser

  def _check_arg_dependencies(self, parser, args):
    for name, short, param in self.parameters:
      if 'depends' in param and getattr(args, name, None) and not getattr(args, param['depends'], None):
        parser.error(
          'argument --{} (-{}) requires --{} (-{}) to be present.'.format(
            name, short, param['depends'], self._find_param(param['depends'])[1]
          )
        )

  def auto(self, root=True):
    if root:
      self.become_root()
    self.parse_args()
    self.execute_playbook()

  def become_root(self):
    if os.geteuid() != 0:
        # -n disables password prompt, when sudo isn't configured properly
        os.execvp('sudo', ['sudo', '-n', '--'] + sys.argv)

  def parse_args(self, args=None):
    parser = self._build_argparser()

    args = parser.parse_args(args)
    self._check_arg_dependencies(parser, args)

    self._parsed_args = args

  def _check_playbook(self):
    if not self.playbook:
      raise ValueError('no playbook given')
    if not os.path.isabs(self.playbook):
      raise ValueError('path to playbook must be absolute')
    if not os.path.isfile(self.playbook):
      raise ValueError('playbook must exist and must not be a link')

  def _get_playbook_executor(self):
    variable_manager = VariableManager()
    loader = DataLoader()
    inventory = Inventory(loader=loader, variable_manager=variable_manager, host_list=['localhost'])
    variable_manager.set_inventory(inventory)
    variable_manager.set_host_variable(inventory.localhost, 'ansible_python_interpreter', sys.executable)

    for name in vars(self._parsed_args):
      variable_manager.set_host_variable(inventory.localhost, 'ubrspc_' + name, getattr(self._parsed_args, name))

    return PlaybookExecutor(
      playbooks=[self.playbook],
      inventory=inventory,
      variable_manager=variable_manager,
      loader=loader,
      options=Options(
        connection='local',
        module_path=None,
        forks=100,
        listhosts=False, listtasks=False, listtags=False, syntax=False,
        become=None, become_method=None, become_user=None, check=False
      ),
      passwords={},
    )

  def execute_playbook(self):
    self._check_playbook()
    self._get_playbook_executor().run()