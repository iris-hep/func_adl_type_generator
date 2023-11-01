import argparse
from collections import defaultdict
from dataclasses import dataclass
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table

valid_tests = ["jets_uncalib", "jets_calib", "met", "error_bad_argument"]


def run_command(cmd: str | List[str]):
    """Run a command and dump the resulting output to logging,
    depending on the return code.

    Args:
        cmd (str): Command to run
    """
    if not isinstance(cmd, list):
        cmd = [cmd]

    command_line = (
        "powershell -c " + ";".join(cmd) if len(cmd) > 1 else f"powershell {cmd[0]}"
    )
    logging.debug(f"Running command: {command_line}")

    try:
        result = subprocess.run(
            command_line,
            capture_output=True,
            text=True,
        )

        level = logging.INFO
        if result.returncode != 0:
            level = logging.ERROR

        logging.log(level, f"Result code from running {cmd}: {result.returncode}")
        for line in result.stdout.split("\n"):
            logging.log(level, f"stdout: {line}")
        for line in result.stderr.split("\n"):
            logging.log(level, f"stderr: {line}")

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to execute (return code {result.returncode}): {command_line}"
            )
    except Exception:
        logging.error("Exception was thrown running the following commands:")
        for ln in cmd:
            logging.error(f"  {ln}")
        raise


def create_type_json(
    release: str, clean: bool, location: Path, cmd_location: Path
) -> Path:
    """Create the type json file for a release.

    Args:
        release (_type_): Release name - an image tag
        clean (_type_): If true, then refresh even if yaml file is present.
    """
    logging.info(f"Building JSON file for {release}")

    # Can we skip?
    yaml_path = location / f"{release}.yaml"
    if yaml_path.exists() and (not clean):
        logging.debug(f"YAML type file for {release} already exists. Not rebuilding")
        return yaml_path

    # Do the build.
    logging.debug(f"Running container to build json type file for {release}")
    run_command(
        f"{cmd_location}/func-adl-types-atlas/scripts/build_xaod_edm.ps1"
        # f" {release} {yaml_path}"
    )
    logging.debug(f"Finished building json type file for {release}")

    return yaml_path


def create_python_package(
    release: str, clean: bool, json_location: Path, location: Path
) -> Path:
    """Given the type json file already exists, create the python
    package for the full type information.

    Args:
        release (str): The name of the release
        clean (bool): If true, remake the package from scratch.
                    Otherwise, only if it isn't there already.
        json_location (Path): Location of the json yaml file
        location (Path): Directory to house the created package

    Returns:
        Path: Location of the package
    """
    logging.info(f"Creating python package for release {release}")

    # See if we can bail out quickly
    package_location = location / release
    if package_location.exists() and (not clean):
        logging.debug(
            f"Python package for release {release} already exists. Not rebuilding."
        )
        return package_location

    # Re-create it.
    commands = []
    commands.append(
        f"sx_type_gen {json_location.absolute()} --output_directory"
        f" {package_location.absolute()}"
    )
    run_command(commands)

    # Next we need to find the package - the actual name of the folder might vary a
    # little bit due to the release series.

    return package_location


def do_build_for_release(release, args):
    yaml_location = create_type_json(
        release, args.clean, args.type_json, args.command_location
    )
    return create_python_package(release, args.clean, yaml_location, args.type_package)


def do_build(args):
    """Iterator that builds a package for each release.

    Args:
        args (): Command line arguments

    Yields:
        Path: THe path where the package is located
    """
    for r in args.release:
        do_build_for_release(r, args)
    return 0


def do_test(args):
    """After making sure that the packages are built, run the requested tests

    Args:
        args (): Command line arguments
    """
    for r in args.release:
        package_path = do_build_for_release(r, args)
        logging.debug(f"Running tests for release {r} in {package_path}")

        # Build the commands to create the env and setup/run the test.
        commands = []

        test_packages_path = Path(__file__).parent / "test_packages.py"
        assert (
            test_packages_path.exists()
        ), f"Configuration error: cannot find {test_packages_path}"

        logging.debug("About to create the temp directory")
        with tempfile.TemporaryDirectory() as release_dir_tmp:
            release_dir = release_dir_tmp if args.test_dir is None else args.test_dir

            commands.append(f"cd {release_dir}")
            commands.append("python -m venv .venv")
            commands.append(". .venv/Scripts/Activate.ps1")
            commands.append("python -m pip install --upgrade pip")

            # Install the package. We want to run locally, so need to install
            # a special flavor of func_adl_servicex.
            commands.append("python -m pip install func_adl_servicex[local]")
            commands.append(f"python -m pip install -e {package_path.absolute()}")

            # Copy over the script to make it easy to "run".
            shutil.copy(test_packages_path.absolute(), release_dir)

            # Commands to run the scripts
            all_tests = args.test if len(args.test) > 0 else valid_tests
            test_args = " ".join([f"--test {t}" for t in all_tests])
            verbose_arg = (" -" + "v" * int(args.verbose)) if args.verbose > 0 else ""

            commands.append(f"python test_packages.py {test_args}{verbose_arg}")

            # Finally, run the commands.
            logging.debug(f"Running tests for release {r} - commands are:")
            for cmd in commands:
                logging.debug(f"  {cmd}")
            run_command(commands)
    return 0


@dataclass
class ReleaseInfo:
    """Information about a release"""

    has_type_json: bool = False
    has_package: bool = False


def do_list(args):
    """Look through all the types and releases and report which are built
    in a table to the user"""

    info = defaultdict(ReleaseInfo)

    # first, look for the type json files
    for f in Path(args.type_json).glob("*.yaml"):
        info[f.stem].has_type_json = True

    # Next, lets look at the package directory for releases
    for f in Path(args.type_package).glob("*"):
        info[f.name].has_package = True

    # Dump the info out as a rich table
    table = Table(title="Release Information")
    table.add_column("Release", justify="right", style="cyan", no_wrap=True)
    table.add_column("Type JSON", justify="right", style="magenta", no_wrap=True)
    table.add_column("Python Package", justify="right", style="green", no_wrap=True)

    for r in info:
        table.add_row(
            r,
            "Yes" if info[r].has_type_json else "No",
            "Yes" if info[r].has_package else "No",
        )

    console = Console()
    console.print(table)


def do_delete(args):
    """Delete the release packages"""
    for r in args.release:
        # Delete the type packages
        package_path = Path(args.type_package) / r
        if package_path.exists():
            logging.debug(f"Removing package {package_path}")
            shutil.rmtree(package_path)

        # Delete the type json file
        json_path = Path(args.type_json) / f"{r}.yaml"
        if json_path.exists():
            logging.debug(f"Removing type json {json_path}")
            json_path.unlink()
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="atlas_release_type_builder",
        description="Build and test atlas release types",
        epilog="Building type libraries can take considerable time. Unless the --clean"
        " option is used, previous outputs are used rather than regenerating from "
        "scratch.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Verbosity Level (-v, or -vv))",
    )

    commands = parser.add_subparsers(help="sub-command help")

    # The "build" an atlas release command
    build_command = commands.add_parser(
        "build", help="Build type library for a release"
    )

    def add_build_args(parser, add_release=True):
        if add_release:
            parser.add_argument(
                "release", type=str, help="List of releases to build", action="append"
            )
            parser.add_argument(
                "--clean",
                type=bool,
                action=argparse.BooleanOptionalAction,
                default=False,
            )
        parser.add_argument(
            "--type_json",
            type=Path,
            default=Path("../type_files"),
            help="Location where yaml type files should be written",
        )
        parser.add_argument(
            "--type_package",
            type=Path,
            default=Path(
                "../type_packages",
                help="Location where the python type package should be created",
            ),
        )
        parser.add_argument(
            "--command_location",
            type=Path,
            default=Path("../../"),
            help="Location of the scripts to run to build the type json file",
        )

    add_build_args(build_command)
    build_command.set_defaults(func=do_build)

    # The test command
    test_command = commands.add_parser("test", help="Run tests for a release")
    test_command.add_argument(
        "--test", choices=valid_tests, default=[], action="append"
    )
    test_command.add_argument(
        "--test_dir",
        type=Path,
        help="Path to place (and leave) test directory",
        default=None,
    )
    add_build_args(test_command)
    test_command.set_defaults(func=do_test)

    # The list command - list all releases that are built one way or the other.
    list_command = commands.add_parser("list", help="List all releases")
    list_command.set_defaults(func=do_list)
    add_build_args(list_command, add_release=False)

    # delete command - will delete a release(s) (type and package files).
    delete_command = commands.add_parser("delete", help="Delete a release")
    add_build_args(delete_command)
    delete_command.set_defaults(func=do_delete)

    args = parser.parse_args()

    # Global flags
    logging.basicConfig()
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        if int(args.verbose) > 1:
            logging.getLogger().setLevel(logging.DEBUG)

    # Now execute the command
    if not hasattr(args, "func"):
        logging.error("No command found on command line")
        parser.print_help()
        exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
