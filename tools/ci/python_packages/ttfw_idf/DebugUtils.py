# Copyright 2020 Espressif Systems (Shanghai) PTE LTD
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import unicode_literals
from io import open
from tiny_test_fw import Utility
import debug_backend
import logging
import pexpect
import pygdbmi.gdbcontroller


class CustomProcess(object):
    def __init__(self, cmd, logfile, verbose=True):
        self.verbose = verbose
        self.f = open(logfile, 'w')
        if self.verbose:
            Utility.console_log('Starting {} > {}'.format(cmd, self.f.name))
        self.pexpect_proc = pexpect.spawn(cmd, timeout=60, logfile=self.f, encoding='utf-8')

    def __enter__(self):
        return self

    def close(self):
        self.pexpect_proc.terminate(force=True)

    def __exit__(self, type, value, traceback):
        self.close()
        self.f.close()


class OCDBackend(object):
    def __init__(self, logfile_path, target, cfg_cmds=[], extra_args=[]):
        # TODO Use configuration file implied by the test environment (board)
        self.oocd = debug_backend.create_oocd(chip_name=target,
                                              oocd_exec='openocd',
                                              oocd_scripts=None,
                                              oocd_cfg_files=['board/esp32-wrover-kit-3.3v.cfg'],
                                              oocd_cfg_cmds=cfg_cmds,
                                              oocd_debug=2,
                                              oocd_args=extra_args,
                                              host='localhost',
                                              log_level=logging.DEBUG,
                                              log_stream_handler=None,
                                              log_file_handler=logging.FileHandler(logfile_path, 'w'),
                                              scope=None)
        self.oocd.start()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.oocd.stop()

    def cmd_exec(self, cmd):
        return self.oocd.cmd_exec(cmd)


class GDBBackend(object):
    def __init__(self, logfile_path, elffile_path, target, gdbinit_path=None, working_dir=None):
        self.gdb = debug_backend.create_gdb(chip_name=target,
                                            gdb_path='xtensa-{}-elf-gdb'.format(target),
                                            remote_target=None,
                                            extended_remote_mode=False,
                                            gdb_log_file=logfile_path,
                                            log_level=None,
                                            log_stream_handler=None,
                                            log_file_handler=None,
                                            scope=None)
        if working_dir:
            self.gdb.console_cmd_run('directory {}'.format(working_dir))
        self.gdb.exec_file_set(elffile_path)
        if gdbinit_path:
            try:
                self.gdb.console_cmd_run('source {}'.format(gdbinit_path))
            except debug_backend.defs.DebuggerTargetStateTimeoutError:
                # The internal timeout is not enough on RPI for more time consuming operations, e.g. "load".
                # So lets try to apply the commands one-by-one:
                with open(gdbinit_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if len(line) > 0 and not line.startswith('#'):
                            self.gdb.console_cmd_run(line)
                            # Note that some commands cannot be applied with console_cmd_run, e.g. "commands"

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        try:
            self.gdb.gdb_exit()
        except pygdbmi.gdbcontroller.NoGdbProcessError as e:
            #  the debug backend can fail on gdb exit when it tries to read the response after issuing the exit command.
            Utility.console_log('Ignoring exception: {}'.format(e), 'O')
        except debug_backend.defs.DebuggerTargetStateTimeoutError:
            Utility.console_log('Ignoring timeout exception for GDB exit', 'O')