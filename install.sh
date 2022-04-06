git clone --depth 1 https://github.com/pybind/pybind11
git clone  https://github.com/wjakob/nanobind

cd nanobind
git checkout b4642b225171903f3c0747f55e1b2fe146838d54
git submodule update --init --recursive

cmake .
make
cd ..

# Install python boost as a system wide module.
#
# We select the latest version on March 2022, which was from December 2021.
# See https://www.boost.org/users/history/version_1_78_0.html
#
# wget https://boostorg.jfrog.io/artifactory/main/release/1.78.0/source/boost_1_78_0.tar.bz2
# tar --bzip2 -xf boost_1_78_0.tar.bz2