import pathlib

from setuptools import setup

pkg_name = 'perf_timer'
base_dir = pathlib.Path(__file__).parent
with open(base_dir / 'src' / pkg_name / '_version.py') as f:
    version_globals = {}
    exec(f.read(), version_globals)
    version = version_globals['__version__']

setup(
    name=pkg_name,
    description='An indispensable performance timer for Python',
    long_description='''
PerfTimer is an instrumenting timer which provides an easy way to
get insight into call count and average execution time of a function
or piece of code during a real session of your program.

Use cases include:
  * check the effects of algorithm tweaks, new implementations, etc.
  * confirm the performance of a library you are considering under
  actual use by your app (as opposed to upstream's artificial
  benchmarks)
  * measure CPU overhead of networking or other asynchronous I/O
  (currently supported: OS threads, Trio async/await)
''',
    long_description_content_type='text/markdown',
    version=version,
    author='John Belmonte',
    author_email='john@neggie.net',
    url='https://github.com/belm0/perf-timer',
    license='MIT',
    packages=[pkg_name],
    package_dir={'': 'src'},
    install_requires=[],
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Framework :: Trio',
    ],
)
