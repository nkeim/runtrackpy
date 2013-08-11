"""Support functions."""
# Copyright 2013 Nathan C. Keim
#
#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation; either version 3 of the License, or (at
#your option) any later version.
#
#This program is distributed in the hope that it will be useful, but
#WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program; if not, see <http://www.gnu.org/licenses>.

import path
import os, contextlib
import ConfigParser

def readSingleCfg(filename):
    """Reads a single section from the .ini file 'filename'.
    
    Returns a dictionary; empty if the file doesn't exist.
    """
    if filename is None or not os.path.exists(filename):
        return {}
    cp = ConfigParser.SafeConfigParser()
    cp.readfp(open(filename))
    secs = cp.sections()
    if len(secs) != 1:
        raise IOError('Expected one section in "%s"' % filename)
    return dict(cp.items(secs[0]))
class DirBase(object):
    """Basis for directory-based data accessors.
    
    Attributes:
        'path' is what's passed to the constructor.
        'p' is what should be used to find enclosed files (instance of path.path).

    Call to use as a chdir() context manager.
    """
    def __init__(self, loc='.'):
        self.path = str(loc)
        self.p = path.path(self.path).abspath()
    name = property(lambda self: self.p.basename(),
            doc='Name of this directory')
    parentname = property(lambda self: (self.p / '..').basename(),
            doc='Name of parent directory')
    def __repr__(self):
        return '%s: %s' % (self.__class__.__name__, self.p)
    def __str__(self):
        return self.p
    @contextlib.contextmanager
    def __call__(self):
        curdir = os.getcwd()
        try:
            os.chdir(self.p)
            yield
        finally:
          os.chdir(curdir) 

