# func_adl_type_generator
Package to drive the building of type files for `func_adl`

## Introduction

This package contains some handy command-line tools as well as a workflow to build type files. This is part of the [ServiceX eco-system][https://github.com/ssl-hep/ServiceX].

`func_adl` type files contain both type information for complex transformer runs against data formats like ATLAS' `xAOD`. The type files contain both type information for all accessible data and config instructions for the software that runs.

Generating these type files is a multi-step process:

1. Code must run against a source image to understand the type model, and dump it to a model agnostic `yaml` file.
1. Code must translate that `yaml` file into python typeshed files.
1. Those packages need to be uploaded to `pypi` so they can be installed by the physicist.

This package contains code and a GitHub workflow to manage this.

The actual work is done by two different packages:

* `func-adl-types-atlas` - reads the type information from an ATLAS executable and dumps them to a `yaml` file.
* `func_adl_servicex_type_generator` - translates the `yaml` file into python code and typeshed files.

The code in these two packages is not included here because they must be versioned, and different parts of the process will evolve as their version evolves.

## Usage

Some notes:

* Please make sure all packages that this uses are tagged in github so the versions and changes can be carefully tracked!
* If you want to develop the packages to add new features, it is best to run things locally on your development machine. See XX for instructions. However, it is possible to use this CI to do development work.

### Production Releases via the CI

The nice thing about the CI is it enforces a uniform, clean, and reproducible workflow for building these type files.

## Releasing New Versions

To release the new versions of func-adl-types-atlas and func_adl_servicex_type_generator follow these steps:

1. Follow the release instructions in the repository you are updating
2. Edit the release.yaml found in the .github folder in this repo to match the correspoding tags in the package you are updating.
3. Run the release workflow in order to test locally that the changes made work as expected.
4. Create a release and new tag, this with automatically update the packages on PyPi.

