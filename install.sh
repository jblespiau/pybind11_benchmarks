git clone --depth 1 https://github.com/pybind/pybind11
git clone --depth 1 https://github.com/wjakob/nanobind


# We select the latest version on March 2022, which was from December 2021.
# See https://www.boost.org/users/history/version_1_78_0.html

wget https://boostorg.jfrog.io/artifactory/main/release/1.78.0/source/boost_1_78_0.tar.bz2
tar --bzip2 -xf boost_1_78_0.tar.bz2
