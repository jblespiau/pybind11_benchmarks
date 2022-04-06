# pybind11 & nanobind benchmarks

The author believes that:

- `pybind11` can be improved significantly, e.g. 
  - caching the type look-up into a static variable is a very large optimization which should be done first.
  - using a better hashmap than `std::unsorted_map` should be impactful too
  - for the compilation time, splitting into headers and cpp files should help a lot (https://github.com/pybind/pybind11/pull/2445)
- having strong automated and reproducible benchmarks is key to this procedure.

Thus, this repository extracts, robustifies (in particular for reprodicubility) and extends the benchmarks available at https://github.com/wjakob/nanobind, to drive the developement and provide arguments to convince the `pybind11` decision board that some changes are required.

The goal is to be able, in addition to a CL, to provide the material to justify that a change speed up pybind11 code by X%.

## Running

On Linux, with python 3.9 installed:

```
pip install requirements.txt
./install.sh
python3 generate_files.py
```

Contributions are welcomed, in particular to add support for more platforms (OSX mainly), or additional benchmarks.

## Technical details

### Supported platforms

Currently, only some Linux-based system is supported (mainly for `apt-get`, but MacOs should be easy to adapt.

### Dynamic linking 

`pybind11` is a header-only library, while `boost.python` and `nanobind` are shared libraries.

For Boost, given we do not target modifying boost to measure performance impact, we simply install the `libboost-python-dev` package.

For `nanobind`, we clone the repository, and build it.

