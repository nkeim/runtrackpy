#!/usr/bin/env python

from distutils.core import setup

setup(
    name='bigtracks',
    version='0.1.1',
    author='Nathan C. Keim',
    author_email='nkeim@seas.upenn.edu',
    url='https://github.com/nkeim/bigtracks',
    packages=['bigtracks'],
    install_requires=['path.py', 'trackpy'],
    )
