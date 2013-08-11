#!/usr/bin/env python

from distutils.core import setup

setup(
    name='runtrackpy',
    version='0.1.2',
    author='Nathan C. Keim',
    author_email='nkeim@seas.upenn.edu',
    url='https://github.com/nkeim/runtrackpy',
    packages=['runtrackpy'],
    install_requires=['path.py', 'trackpy', 'pantracks'],
    test_suite = 'nose.collector'
    )
