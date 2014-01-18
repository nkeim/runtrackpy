# Overview

`runtrackpy` is an attempt to provide a somewhat friendly front-end for tracking particles in a series of video images. It uses a special [accelerated version of `trackpy`](http://github.com/nkeim/trackpy/) (original [here](http://github.com/tacaswell/trackpy/) ), Tom Caswell's Python implementation of the [Crocker-Grier particle-tracking algorithm](http://dx.doi.org/10.1006/jcis.1996.0217). 

You can see it in action in an [example IPython notebook](http://nbviewer.ipython.org/urls/raw.github.com/nkeim/runtrackpy/master/examples/basic-tracking-demo.ipynb).

Its principal virtues are

- Like `trackpy`, it is free and open-source (GPL) and runs in a free environment.
- It scales efficiently to large datasets, limited only by disk space. In principle, available RAM limits only the size of a single frame.
- It outputs to a standard numerical file format, HDF5, which is readable by MATLAB, IDL, etc. (although there, you may be limited by available RAM).
- It includes tools for efficiently reading its particle tracks databases, which may be used as a foundation for your own analysis.

`runtrackpy` was written by [Nathan Keim](http://www.seas.upenn.edu/~nkeim/), a member of the [Penn Complex Fluids Lab](http://arratia.seas.upenn.edu).

# Installation

The easiest route is to first install the free [Anaconda](https://store.continuum.io/cshop/products/) Python distribution from [Continuum Analytics](http://continuum.io) or [Canopy](https://www.enthought.com/products/canopy/) from [Enthought](https://www.enthought.com). 

Otherwise, the following Python packages are needed for `runtrackpy` and the required version of `trackpy` (see below):

- `numba`
- the Python Imaging Library (PIL)
- `pip` (for easy installation)
- `scipy` and `numpy`
- `pandas`
- `pytables`
- `ipython` and `pyzmq` for parallel computing 
- `tornado` to display the example IPython notebooks
- `matplotlib` (optional)

## Easy

`runtrackpy` uses a special version of `trackpy` that has been accelerated with `numba`, and given a slightly modified API to permit handling of large datasets. This is currently found on [GitHub](http://github.com/nkeim/trackpy/). If you want an easy way to read the tracks files that are produced, and/or to test `runtrackpy`, you will also need [`pantracks`](http://github.com/nkeim/pantracks/).

The easiest way to install all packages is with `pip`, *if* `git` is also installed (which it should already be on Mac or Linux):

    pip install 'git+http://github.com/nkeim/trackpy/@numba#egg=trackpy'
    pip install 'git+http://github.com/nkeim/pantracks/#egg=pantracks'
    pip install 'git+http://github.com/nkeim/runtrackpy/#egg=runtrackpy'

Remember to use double quotes (") on Windows. *Tip for novices: Be sure that the `pip` you are running belongs to the Python installation you'll use for tracking (e.g. anaconda).*

This also works for upgrading to the latest version. If you want to muck about with the source code, add a `-e` after `pip install`, and a `src` directory will be created in your current directory.

## Manually

Alternately, download the source of each package and run

    python setup.py install

in each source directory.

If you choose not to use `pip` or `easy_install`, you will need to make sure that the `path.py` package is also installed. 

## Tests

A check of basic functionality (similar to what's in the example notebook) can be run with `nosetests`.

# Documentation

Docstrings in the source are reasonably complete, for now. There is also a demonstration IPython notebook in the `examples` directory; you can view it [here](http://nbviewer.ipython.org/urls/raw.github.com/nkeim/runtrackpy/master/examples/basic-tracking-demo.ipynb).
