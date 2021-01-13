#   Copyright 2020 Eric Chang
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


"""This package provides classes for building pybind11 extensions.
"""

from typing import Optional

import os
import re
import sys
import platform
import subprocess as sp
from pathlib import Path

from packaging import version
from setuptools import Extension
from setuptools.command.build_ext import build_ext


class CMakePyBind11Extension(Extension):
    def __init__(self, name: str, sourcedir: str = ".") -> None:
        Extension.__init__(self, name, sources=[])
        self.sourcedir = str(Path(sourcedir).resolve())


class CMakePyBind11Build(build_ext):
    user_options = build_ext.user_options
    user_options.append(("build-type=", None, "CMake build type"))
    user_options.append(("build-log=", "", "build message output log"))

    def initialize_options(self) -> None:
        build_ext.initialize_options(self)
        self.build_type: str = "Debug"
        self.build_log: str = ""

    def run(self) -> None:
        try:
            out = sp.check_output(["cmake", "--version"])
        except OSError:
            err = RuntimeError(
                "CMake must be installed to build the following extensions: "
                f"{', '.join(e.name for e in self.extensions)}"
            )
            self._log(str(err), error=True)
            raise err

        if platform.system() == "Windows":
            cmake_version = re.search(r"version\s*([\d.]+)", out.decode()).group(1)
            if version.parse(cmake_version) < version.parse("3.1.0"):
                err = RuntimeError("CMake >= 3.1.0 is required on Windows")
                self._log(str(err), error=True)
                raise err

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext: CMakePyBind11Extension) -> None:
        # setup CMake initialization and build commands
        version = self.distribution.get_version()
        ext_dir = Path(self.get_ext_fullpath(ext.name)).parent.resolve()
        init_cmd = [
            "cmake",
            f"-S{ext.sourcedir}",
            f"-B{self.build_temp}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={ext_dir}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
            f"-DCMAKE_BUILD_TYPE={self.build_type}",
        ]
        build_cmd = [
            "cmake",
            "--build",
            self.build_temp,
            "--",
        ]

        # handle Windows CMake arguments
        if platform.system() == "Windows":
            if sys.maxsize > 2 ** 32:
                init_cmd.append("-A")
                init_cmd.append("x64")
            build_cmd.append("/m")

        # set up parallel build arguments
        num_workers = self._get_num_workers()
        self._log(f"[{ext.name}] parallel={num_workers}")
        build_cmd.append(f"-j{num_workers}")

        # run CMake
        Path(self.build_temp).mkdir(parents=True, exist_ok=True)
        self._log(f"[{ext.name}] Building {ext.name} version: {version}")
        self._log(f"[{ext.name}] CMake init command: {' '.join(init_cmd)}")
        self._log(f"[{ext.name}] CMake build command: {' '.join(build_cmd)}")

        if self.build_log:
            with open(self.build_log, "a") as f:
                sp.check_call(init_cmd, stdout=f, stderr=sp.STDOUT)
                sp.check_call(build_cmd, stdout=f, stderr=sp.STDOUT)
        else:
            sp.check_call(init_cmd, stdout=None, stderr=None)
            sp.check_call(build_cmd, stdout=None, stderr=None)

        # generate stubs
        # subprocess.check_call(["./gen_stubs.sh"])

        # Add an empty line for cleaner output

    def _log(self, msg: str, error: bool = False) -> None:
        print(f"build log is: {self.build_log}, parallel is: {self.parallel}")
        raise ValueError("oops")
        if self.build_log:
            with open(self.build_log, "a") as f:
                if error:
                    f.write("[ERROR] ")
                f.write(msg)
                f.write("\n")

    def _get_num_workers(self) -> int:
        workers: Optional[int] = self.parallel
        if workers is None:
            return 1
        elif workers == 0:
            workers = os.cpu_count()  # may return None
            return 1 if workers is None else max(workers // 2, 1)
        else:
            return workers
