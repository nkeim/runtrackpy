"""Access tracks data files.

Provides a context manager so that the underlying HDF5 file is always
closed when you're done using it, which is important in long-running 
interactive sessions.

Alternately:
    bt = BigTracks('bigtracks.h5')
    framedata = bt.get_frame(5) # Opens file
    nframes = bt.maxframe() # Opens file again
"""
#   Copyright 2013 Nathan C. Keim
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
import contextlib
import numpy as np
from path import path
import pandas, tables

class BigTracks(object):
    """Object to access a PyTables HDF5 file containing particle tracking data.

    Each of the data-reading methods opens the file and then closes it, to avoid
    data consistency issues. However, instances of this class can also be used as
    context managers, so that the file is opened just once for multiple operations.

    Example:
        bt = BigTracks('bigtracks.h5')
        with bt: # Opens file once --- best if you're planning to do a lot
            framedata = bt.get_frame(5)
            nframes = bt.maxframe()
        frametracks = bt.get_frame(5) # This works too!

    Individual frames can also be retrieved as dictionary items:
        frametracks = bt[5]
    If the frame is not in the file, an IndexError will be raised.
    """
    def __init__(self, filename='output/bigtracks.h5'):
        """NOTE: This does not open the file."""
        self.filename = filename
        self._openfile = None
        self.table = None
    def __enter__(self):
        if self._openfile is not None:
            # Someone is trying to enter the context twice, without exiting first.
            # To permit this, we'd have to use some kind of stack or counter to 
            # decide when to close the file (i.e. which is the outermost context).
            # For now, just make it illegal.
            raise RuntimeError('This BigTracks instance is already being used as a context.')
        try:
            try:
                self._openfile = tables.openFile(self.filename, 'r')
                self.table = self._openfile.root.bigtracks
            except (tables.exceptions.HDF5ExtError, AttributeError):
                raise IOError('File %s appears to be corrupted.' \
                        % path(self.filename).abspath())
        except:
            if self._openfile is not None:
                self._openfile.close()
                self._openfile = None
                self.table = None
            raise
        return self
    def __exit__(self, type_, value, traceback):
        if self._openfile is not None:
            self._openfile.close()
            self._openfile = None
            self.table = None
    @contextlib.contextmanager
    def _open_tracks(self):
        """Context for accessing the tracks table. Must use for all pytables calls.
        Opens the file if necessary."""
        if self._openfile is not None:
            yield
        else:
            with self:
                yield
    def query(self, *args, **kw):
        """Perform generalized searches in a bigtracks table.
        
        Behaves like pytables' Table.where(), but returns a DataFrame.
        
        Example: query('particle == 401')"""
        with self._open_tracks():
            return pandas.DataFrame(self.table.readWhere(*args, **kw))
    def get_frame(self, fnum):
        """Load data for a single frame."""
        return self.query('(frame == %i)' % fnum)
    def get_all(self):
        """Return the entire contents of the tracks table."""
        with self._open_tracks():
            return pandas.DataFrame(self.table[:])
    def __getitem__(self, fnum):
        ftr = self.get_frame(fnum)
        if len(ftr):
            return ftr
        else:
            raise IndexError('Frame %s not found' % str(fnum))
    def maxframe(self):
        """Frame number at end of bigtracks file."""
        with self._open_tracks():
            return int(self.table[-1]['frame'])
    def framerange(self):
        """Array of frame numbers in bigtracks file.

        Assumes a contiguous range with step size 1."""
        with self._open_tracks():
            return np.arange(self.table[0]['frame'], self.table[-1]['frame'] + 1)

def dfcrop(df, xmin=-np.inf, xmax=np.inf, ymin=-np.inf, ymax=np.inf, xcol='x', ycol='y'):
    """Crop a particle tracks DataFrame"""
    return df[(df[xcol] > xmin) & (df[xcol] < xmax) & \
            (df[ycol] > ymin) & (df[ycol] < ymax)]
def interpolate_tracks(bigtracks, fnum):
    """Returns tracks data at a non-integer frame number.
    If 'fnum' does not have a fractional part, just use loadFrameTracks().

    Returned DataFrame is indexed arbitrarily, NOT by particle ID.

    'table' is the pytables table from which tracks data will be loaded.
    """
    if not (fnum % 1):
        return bigtracks.get_frame(fnum)
    else:
        with bigtracks:
            frames = bigtracks.framerange(fnum)
            fidx = frames.searchsorted(fnum)
            try:
                fnum0 = frames[fidx - 1]
                fnum1 = frames[fidx]
            except IndexError:
                raise ValueError('Frame %f is outside available data' % fnum)
            ftr0 = bigtracks.get_frame(fnum0).set_index('particle')
            ftr1 = bigtracks.get_frame(fnum1).set_index('particle')
        ftr = ftr0.copy()
        ftr.frame = fnum
        ftr['x'] = ftr0.x + (ftr1.x - ftr0.x) * (fnum % 1)
        ftr['y'] = ftr0.y + (ftr1.y - ftr0.y) * (fnum % 1)
        ftr = ftr.dropna()
        ftr['particle'] = ftr.index.values
        ftr.index = np.arange(len(ftr), dtype=int)
        return ftr

# Diagnostics
def compute_quality(bigtracks, frame_interval=10):
    """Global diagnostics for bigtracks data.
    
    Looks at one out of every 'frame_interval' frames.

    Returns
    ------
    btq : DataFrame indexed by frame number
        btq.N : Number of particles in that frame
        btq.Nconserved : Number of particles in common with first frame.

    See also
    ------
    plotBTQuality()
    """
    with bigtracks:
        frames = bigtracks.framerange()[::frame_interval]
        btq = pandas.DataFrame({'N': -1, 'Nconserved': -1}, index=frames, dtype=int)
        ftr0 = None
        for fnum in frames:
            ftr = bigtracks.get_frame(fnum).set_index('particle')
            if ftr0 is None: ftr0 = ftr
            btq.N[fnum] = len(ftr)
            btq.Nconserved[fnum] = (ftr.frame - ftr0.frame).count()
    return btq

def plot_quality(btquality):
    """Make diagnostic plot of output of computeBTQuality()."""
    import pylab as pl
    btq = btquality
    pl.figure()
    pl.plot(btq.index, (btq.N - btq.N.ix[0]) / float(btq.N.ix[0]), 'bo')
    pl.ylabel('$(N - N_0) / N_0$', color='b')
    pl.xlabel('Frame')
    pl.twinx()
    pl.plot(btq.index, -(btq.Nconserved - btq.N.ix[0]) / float(btq.N.ix[0]), 'r^')
    pl.ylabel('Fraction dropped', color='r')
