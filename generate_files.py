import random
import subprocess
import itertools
import collections
import importlib.machinery
import collections
import os
import time
import sys

import matplotlib.pyplot as plt
import numpy as np

from sysconfig import get_paths as gp

# A list of strings representing the recognized file suffixes for extension modules.
# https://docs.python.org/3/library/importlib.html#importlib.machinery.EXTENSION_SUFFIXES
_EXTENSION_SUFFIX = importlib.machinery.EXTENSION_SUFFIXES[0]

_PYBIND11_PATH = os.path.join(os.getcwd(), 'pybind11/include')
_NANOBIND_PATH = os.path.join(os.getcwd(), 'nanobind/include')
_BOOST_PATH = os.path.join(os.getcwd(), 'boost_1_78_0')
_CMD_BASE = [
    'clang++',
    '-shared',
    # We compile with the latest compiler. nanobind requires it, and it's a
    # fair comparison to use it for all benchmarks.
    '-std=c++17',
    '-rpath', '..',
    '-I', gp()['include'],
    '-I', _PYBIND11_PATH,
    # Boost includes.
    # '-I', _BOOST_PATH,
    # '-rpath', f'{_BOOST_PATH}/stage/lib',
    # f'-L{_BOOST_PATH}/stage/lib',
    # Nanobind includes
    '-I', _NANOBIND_PATH,
    '-rpath', 'nanobind/tests',
    '-Lnanobind/tests',
    # '-rpath', 'nanobind',
    # TODO(jblespiau): Is this useful?
    '-Wno-deprecated-declarations',
    '-fno-stack-protector',

    # For boost, it fails without this flag with:
    # relocation R_X86_64_32 against `.bss' can not be used when making a
    # shared object; recompile with -fPIC,
    '-fPIC'
]

_OSX_FLAGS = ['-mcpu=apple-a14', '-undefined', 'dynamic_lookup']


def _gen_func(f, lib):
  """Generates all permutations of addition functions of 6 types of arguments."""
  types = ['uint16_t', 'int32_t', 'uint32_t', 'int64_t', 'uint64_t', 'float']
  if lib == 'boost':
    prefix = 'py::'
  else:
    prefix = 'm.'
  for i, t in enumerate(itertools.permutations(types)):
    args = f'{t[0]} a, {t[1]} b, {t[2]} c, {t[3]} d, {t[4]} e, {t[5]} f'
    f.write('    %sdef("test_%04i", +[](%s) { return a+b+c+d+e+f; });\n' %
            (prefix, i, args))


def _gen_class(f, lib):
  """Generates structs with 6 fields and a `sum` function returning their sum."""
  types = ['uint16_t', 'int32_t', 'uint32_t', 'int64_t', 'uint64_t', 'float']

  for i, t in enumerate(itertools.permutations(types)):
    if lib == 'boost':
      prefix = ''
      postfix = f', py::init<{t[0]}, {t[1]}, {t[2]}, {t[3]}, {t[4]}, {t[4]}>()'
    else:
      prefix = 'm, '
      postfix = ''

    f.write(f'    struct Struct{i} {{\n')
    f.write(
        f'        {t[0]} a; {t[1]} b; {t[2]} c; {t[3]} d; {t[4]} e; {t[5]} f;\n'
    )
    f.write(
        f'        Struct{i}({t[0]} a, {t[1]} b, {t[2]} c, {t[3]} d, {t[4]} e, {t[5]} f) : a(a), b(b), c(c), d(d), e(e), f(f) {{ }}\n'
    )
    f.write('        float sum() const { return a+b+c+d+e+f; }\n')
    f.write('    };\n')
    f.write(f'    py::class_<Struct{i}>({prefix}\"Struct{i}\"{postfix})\n')
    if lib != 'boost':
      f.write(
          f'        .def(py::init<{t[0]}, {t[1]}, {t[2]}, {t[3]}, {t[4]}, {t[5]}>())\n'
      )
    f.write(f'        .def("sum", &Struct{i}::sum);\n\n')

    if i > 250:
      break


_OPT_FLAGS = {'debug': ['-O0', '-g3'], 'opt': ['-Os', '-g0']}


def gen_file(name, func, libs=('boost', 'pybind11', 'nanobind')):
  """Generates the `.cpp` files for all the libraries.

  The files are generated within a `cpp/` directory.
  """
  if not os.path.isdir('cpp'):
    os.mkdir('cpp/')

  for lib in libs:
    for opt_mode in _OPT_FLAGS:
      with open(f'cpp/{name}_{lib}_{opt_mode}.cpp', 'w') as f:
        if lib == 'boost':
          f.write('#include <boost/python.hpp>\n\n')
          f.write('namespace py = boost::python;\n\n')
          f.write(f'BOOST_PYTHON_MODULE({name}_{lib}_{opt_mode}) {{\n')
        else:
          f.write(f'#include <{lib}/{lib}.h>\n\n')
          f.write(f'namespace py = {lib};\n\n')

          prefix = 'NB' if lib == 'nanobind' else 'PYBIND11'
          f.write(f'{prefix}_MODULE({name}_{lib}_{opt_mode}, m) {{\n')

        func(f, lib)
        f.write('}\n')


_CompilationData = collections.namedtuple('_CompilationData',
                                          ['sizes', 'times'])


def compile_and_run_files(directory, only=('boost', 'pybind11', 'nanobind')):
  """Generates `.cpp` file for the provided libraries, calling `func` for the content.

  Args:
  """
  if not os.path.exists(directory):
    raise ValueError('directory does not exist')

  sizes = {}
  times = {}

  dirs = os.listdir(directory)
  print('Compiling files in', directory)
  for file in dirs:
    name_lib_mode = file.split('.')[0].split('_')
    if len(name_lib_mode) != 3:
      raise AssertionError(
          'The cpp/ directory is expected to contain files of the form '
          f'{{class, func}}_<lib>_<mode>.cpp, found {file}')
    name, lib, opt_mode = name_lib_mode
    if lib not in only:
      continue

    print(f'Processing {name}, {lib}, {opt_mode}')
    opt_flags = _OPT_FLAGS[opt_mode]
    fname_out = name + '_' + lib + '_' + opt_mode + _EXTENSION_SUFFIX
    file_path = os.path.join('cpp', f'{name}_{lib}_{opt_mode}.cpp')
    cmd = _CMD_BASE + opt_flags + [file_path, '-o', fname_out]

    # TODO(jblespiau): Better understand the impact of using a shared library
    # at link time. Reduces the binary size, but requires the shared lib to be
    # installed?
    if lib == 'nanobind':
      cmd += ['-lnanobind']
    elif lib == 'boost':
      cmd += ['-lboost_python39']

    print('Running:', ' '.join(cmd))
    time_before = time.perf_counter()
    try:
      proc = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
      print(proc)
    except subprocess.CalledProcessError as e:
      print(e.output)
      raise
    time_after = time.perf_counter()
    if opt_mode != 'debug':
      subprocess.check_call(['strip', '-x', fname_out])

    bytes_size = os.path.getsize(fname_out)
    sizes[f'{name}_{lib}_{opt_mode}'] = os.path.getsize(fname_out) / (1024 *
                                                                      1024)
    times[f'{name}_{lib}_{opt_mode}'] = time_after - time_before

  return _CompilationData(sizes=sizes, times=times)


def _get_values(mapping, lib_name, names_opt_modes):
  """Returns the metrics from `mapping` for `lib_name` ordered by `names_opt_modes."""
  return [
      mapping[f'{name}_{lib_name}_{mode}'] for name, mode in names_opt_modes
  ]

def _get_labels_and_names_opt_modes(name_lib_opt_mode_list):
  names = set()
  opt_modes = set()
  for name_lib_mode in name_lib_opt_mode_list:
    name, lib, opt_mode = name_lib_mode.split('_')
    names.add(name)
    opt_modes.add(opt_mode)

  names = sorted(names)
  opt_modes = sorted(opt_modes)

  labels = []
  names_opt_modes = []
  for name in names:
    for opt_mode in opt_modes:
      names_opt_modes.append((name, opt_mode))
      labels.append(f'{name} [ {opt_mode} ]')

  return labels, names_opt_modes


def gen_compilation_graphs(name_lib_to_float, title, ylabel, filename):
  """Args:

    name_lib_to_float: Either a mapping of the compilation times, or binary
    size.
  """
  times = name_lib_to_float
  labels, names_opt_modes = _get_labels_and_names_opt_modes(times)

  x = np.arange(len(labels))  # the label locations
  width = 0.25  # the width of the bars

  fig, ax = plt.subplots(figsize=[11.25, 3])

  boost_times = _get_values(times, "boost", names_opt_modes)
  pybind11_times = _get_values(times, "pybind11", names_opt_modes)
  nanobind_times = _get_values(times, "nanobind", names_opt_modes)
  boost_rects = ax.bar(
      x - width,
      boost_times,
      width,
      label='boost',
      align='center',
      edgecolor='black')
  pybind11_rects = ax.bar(
      x,
      pybind11_times,
      width,
      label='pybind11',
      align='center',
      edgecolor='black')
  nanobind_rects = ax.bar(
      x + width,
      [times[f'{name}_nanobind_{mode}'] for name, mode in names_opt_modes],
      width,
      label='nanobind',
      align='center',
      edgecolor='black')

  ax.set_ylabel(ylabel)
  ax.set_title(title)
  ax.set_xticks(x, labels)
  ax.legend()

  ylim = np.max(list(times.values())) * .76
  ax.set_ylim(0, ylim)

  def adj(ann):
    """Limits bars that are too high, and uses a white font."""
    for a in ann:
      if a.xy[1] > ylim * .9:
        a.xy = (a.xy[0], ylim * 0.8)
        a.set_color('white')

  min_times = np.stack([np.asarray(boost_times),
                        np.asarray(pybind11_times),
                        np.asarray(nanobind_times)]).min(axis=0)

  for rectangles, lib_times in [(boost_rects, boost_times),
                                (pybind11_rects, pybind11_times),
                                (nanobind_rects, nanobind_times)]:
    slow_down = np.asarray(lib_times) / min_times
    improvement = [
        '%.2f\n(x %.1f)' % (lib_times[i], v) for i, v in enumerate(slow_down)
    ]
    adj(ax.bar_label(rectangles, labels=improvement, padding=3))

  fig.tight_layout()
  plt.savefig(f'{filename}.png', facecolor='white', dpi=200)
  plt.savefig(f'{filename}.svg', facecolor='white')
  return fig


# Running the extensions and graph construction
class native_module:

  @staticmethod
  def test_0000(a, b, c, d, e, f):
    return a + b + c + d + e + f

  class Struct0:

    def __init__(self, a, b, c, d, e, f):
      self.a = a
      self.b = b
      self.c = c
      self.d = d
      self.e = e
      self.f = f

    def sum(self):
      return self.a + self.b + self.c + self.e + self.f


def runtime_performance():
  print("Getting runtime performances...")

  rtimes = {}
  for name in ['func', 'class']:
    its = 1000000 if name == 'func' else 500000
    for lib in ['python', 'pybind11', 'nanobind', 'boost']:  # nanobind, boost
      for mode in ['debug', 'opt']:
        if lib == 'python':
          # We can use a real module, or the fake class above which acts as
          # a module, but which is faster.
          # m = importlib.import_module('python_module')
          m = native_module
        else:
          m = importlib.import_module(f'{name}_{lib}_{mode}')

        time_before = time.perf_counter()
        if name == 'func':
          for i in range(its):
            m.test_0000(1, 2, 3, 4, 5, 6)
        elif name == 'class':
          for i in range(its):
            m.Struct0(1, 2, 3, 4, 5, 6).sum()

        time_after = time.perf_counter()

        rtimes[f"{name}_{lib}_{mode}"] = (time_after - time_before)

  return rtimes



# import matplotlib as mpl
# mpl.rcParams['hatch.linewidth'] = 5.0 

def gen_performance_graphs(runtimes):
  print("Getting runtime performances graphs...")

  labels, names_opt_modes = _get_labels_and_names_opt_modes(runtimes)
  x = np.arange(len(labels))  # the label locations
  width = 0.22  # the width of the bars

  boost_times = _get_values(runtimes, "boost", names_opt_modes)
  pybind11_times = _get_values(runtimes, "pybind11", names_opt_modes)
  nanobind_times = _get_values(runtimes, "nanobind", names_opt_modes)
  python_times = _get_values(runtimes, "python", names_opt_modes)

  min_times = np.stack([np.asarray(boost_times),
                        np.asarray(pybind11_times),
                        np.asarray(nanobind_times)]).min(axis=0)

  fig, ax = plt.subplots(figsize=[11.25, 3])
  rects1 = ax.bar(x- 1.5*width, boost_times, width, label='boost', align='center', edgecolor='black')
  rects2 = ax.bar(x - width/2, pybind11_times, width, label='pybind11', align='center', edgecolor='black')
  rects3 = ax.bar(x + width/2, nanobind_times, width, label='nanobind', align='center', edgecolor='black')
  rects0 = ax.bar(x + 1.5*width, python_times, width, label='python', align='center', hatch="/", edgecolor='white')
  ax.bar(x + 1.5*width, python_times, width, align='center', edgecolor='black', facecolor='None')

  ax.set_ylabel('Time (seconds)')
  ax.set_title('Runtime performance')
  ax.set_xticks(x, labels)
  ax.legend()
  ylim = np.max(pybind11_times)* .32
  ax.set_ylim(0, ylim)

  def adj(ann):
      for a in ann:
          if a.xy[1] > ylim:
              a.xy = (a.xy[0], ylim * 0.8)
              a.set_color('white')


  improvement = np.array(python_times) / np.array(nanobind_times)
  improvement = ['%.2f\n(x %.1f)' % (python_times[i], v) for i, v in enumerate(improvement)]
  adj(ax.bar_label(rects0, labels=improvement, padding=3))

  improvement = np.array(boost_times) / np.array(nanobind_times)
  improvement = ['%.2f\n(x %.1f)' % (boost_times[i], v) for i, v in enumerate(improvement)]
  adj(ax.bar_label(rects1, labels=improvement, padding=3))

  improvement = np.array(pybind11_times) / np.array(nanobind_times)
  improvement = ['%.2f\n(x %.1f)' % (pybind11_times[i], v) for i, v in enumerate(improvement)]
  adj(ax.bar_label(rects2, labels=improvement, padding=3))

  adj(ax.bar_label(rects3, fmt='%.2f'))

  fig.tight_layout()
  plt.savefig('perf.png', facecolor='white', dpi=200)
  plt.savefig('perf.svg', facecolor='white')
  return fig


cpp_dir = os.path.join(os.getcwd(), 'cpp/')
sys.path.insert(0, cpp_dir)

gen_file('func', _gen_func)
gen_file('class', _gen_class)
compilation_data = compile_and_run_files(cpp_dir)
print(compilation_data)

# compilation_data = _CompilationData(
#     sizes={
#         'class_boost_opt': 3.200624,
#         'class_pybind11_opt': 0.801760,
#         'func_boost_opt': 6.379840,
#         'class_boost_debug': 36.997512,
#         'func_pybind11_debug': 25.215752,
#         'class_pybind11_debug': 28.348160,
#         'func_pybind11_opt': 1.563640,
#         'func_boost_debug': 21.998824,
#         'class_nanobind_opt': 0.29685211181640625, 'class_nanobind_debug': 8.693931579589844, 'func_nanobind_debug': 10.312309265136719, 'func_nanobind_opt': 0.448577880859375,
#     },
#     times={
#         'class_boost_opt': 59.02106701499724,
#         'class_pybind11_opt': 46.46974422399944,
#         'func_boost_opt': 34.67665654800658,
#         'class_boost_debug': 27.64489218899689,
#         'func_pybind11_debug': 29.556745306996163,
#         'class_pybind11_debug': 28.78910167599679,
#         'func_pybind11_opt': 38.6706105129997,
#         'func_boost_debug': 19.3108848510019,
#         'class_nanobind_opt': 17.301341832004255, 'class_nanobind_debug': 15.288980769008049, 'func_nanobind_debug': 12.167448592997971, 'func_nanobind_opt': 17.3487650820025
#     })

gen_compilation_graphs(
    compilation_data.times,
    title='Time (seconds)',
    ylabel='Compilation time',
    filename='times')

gen_compilation_graphs(
    compilation_data.sizes,
    title='Binary size',
    ylabel='Size (MiB)',
    filename='sizes')
