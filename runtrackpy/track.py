"""Utilities to drive the Caswell Python tracking code (as modified by NCK).

Functions of note:
    identify_frame() previews feature identification.
    track2disk() implements a complete tracking workflow.

The 'params' dictionaries required below have the following options:
    For identification:
        'identmod': Name of module in which to find identification function.
            Default: This one.
        'identfunc': Name of identification function. 
            Default: basic bandpass-supbixel algorithm.
        'maxgray': Maximum grayscale value of images (default 0 -> best guess)
        'bright': 0 -> dark particles on light background (default); 1 -> inverse
        [Depending on 'identfunc', the following parameters may be different.]
        'featsize': Expected particle feature radius
        'bphigh': Scale, in pixels, for smoothing images and making them more lumpy
        'maxrg': Cutoff for particle radius of gyration --- how extended particle is
        'threshold': Ignore pixels smaller than this value
        'merge_cutoff': Merge features that are too close to each other.
    For tracking:
        'maxdisp': Radius of region in which to look for a particle in the next frame.
            Set too high, and the algorithm will be overwhelmed with possible matches.
        'memory': How many frames a particle can skip, and still be identified if it has
            not moved past 'maxdisp'.

The 'window' dictionaires limit where and when to look for particles. 
Items 'xmin', 'xmax', 'ymin', and 'ymax' set the spatial limits. 'firstframe' 
and 'lastframe' set the range of frames to track, inclusive; the first frame 
is numbered 1. All values are optional. 

If you are using the runtrackpy.run module, these can be stored in "trackpy.ini" 
and "window.ini" in each movie directory.

Simple example of a do-it-yourself tracking pipeline:
    params = dict(featsize=3, bphigh=0.7, maxrg=100, maxdisp=3)
    mytracks = list(link_dataframes(feature_iter(enumerate(allfiles), params), params))
    # 'mytracks' can then be combined into a single DataFrame with the append() method.
See track2disk() for something much more user-friendly.
"""
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

import os, sys, itertools, importlib
import numpy as np
import scipy.misc
from scipy.spatial import cKDTree
import pandas, tables
import trackpy.feature, trackpy.linking
from . import identification
from .util import readSingleCfg
from .statusboard import StatusFile, Stopwatch, format_td

# I've coded this with 32-bit floats to save disk space and bandwidth.
# The native data type of pandas is a 64-bit float.
# If you have more than ~10^7 particles and/or frames, you want 64 bits.
# Just remove all the casts to 'float32' and 'float64', and redefine the pytables
# columns as Float64Col, and you should be all set.
# Note that there will be pandas trouble if the pytables definition mixes 
# 32- and 64-bit fields.

# Nuts and bolts of individual tracking operations
def identify_frame(im, params, window=None):
    """Identify features in image array 'im' and return a DataFrame

    Uses the function determined and loaded by get_identify_function().
    Loading that function can be expensive, so it's better to get the function
    returned by get_identify_function() and use that yourself if many
    frames are to be processed.
    """
    if float(params.get('bright', 0)):
        im = 1 - im
    return get_identify_function(params)(im, params, window=window)
def get_identify_function(params):
    """Based on the 'identfunc' and 'identmod' elements in 'params', decide which 
    function to use, then pass 'params' to that function. That function
    interprets 'params', processes 'im', and returns a DataFrame with at least
    columns 'x' and 'y', and hopefully 'intensity' and 'rg2'.

    If 'identmod' or 'identfunc' is not specified, the defaults are "."
    and "identify_frame_basic", respectively, where "." refers to this module.

    Because 'identmod' is imported after this module is loaded, it can import
    this module and use functions defined in it, particularly postprocess_features().
    """
    identfunc_name = params.get('identfunc', 'identify_frame_basic')
    identmod_name = params.get('identmod', '.')
    if identmod_name == '.':
        return globals()[identfunc_name]
    else:
        module = importlib.import_module(identmod_name)
        module = reload(module)
        return getattr(module, identfunc_name)

def identify_frame_basic(im, params, window=None):
    """Basic bandpass-subpixel feature identification procedure.

    For cropping the features, 'window' can be a dict of xmin, xmax, ymin, ymax,
    or "file", which uses the "window.ini" file in the current directory.
    
    See module docs for 'params'
    """
    # Parameters
    featsize = int(params.get('featsize', 3))
    bphigh = float(params.get('bphigh', 0.7))
    bplow = int(params.get('bplow', featsize))
    threshold = float(params.get('threshold', 1e-15))
    # Feature identification
    imbp = identification.band_pass(im, bplow, bphigh)
    lm = identification.find_local_max(imbp, featsize, threshold=threshold)
    lmcrop = identification.local_max_crop(imbp, lm, featsize)
    pos, m, r2 = identification.subpixel_centroid(imbp, lmcrop, featsize, struct_shape='circle')
    # Munging
    df = pandas.DataFrame({'x': pos[0,:], 'y': pos[1,:], 'intensity': m, 'rg2': r2})
    return postprocess_features(df, params, window=window)
def postprocess_features(df, params, window=None):
    """Apply standard cuts, cropping, merging to a features DataFrame."""
    # This could be used by custom feature identification functions defined in
    # other files.
    maxrg = float(params.get('maxrg', np.inf))
    merge_cutoff = float(params.get('merge_cutoff', -1))
    # Radius of gyration cut
    feats = df[df.rg2 <= maxrg]
    # Apply crop window
    if window is not None:
        if window == 'file':
            window = get_window()
        feats = feats[(feats.x > window['xmin']) & (feats.x < window['xmax']) & \
                (feats.y > window['ymin']) & (feats.y < window['ymax'])]
    # Merge nearby particles
    if merge_cutoff <= 0:
        return feats
    else:
        return merge_groups(feats, merge_cutoff)
def feature_iter(filename_pairs, params, window=None):
    """Convert a sequence of (frame number, filename) into a sequence of features data.
    
    Note that this uses the track.imread(), not that from e.g. pylab."""
    for fnum, filename in filename_pairs:
        # NOTE that this imread is not like the matplotlib version, which is
        # already normalized.
        # We use this version because importing matplotlib is very expensive.
        ftr = identify_frame(imread(filename, params),
                params, window=window)
        yield fnum, ftr
def imread(filename, params=None):
    """Load a single image, normalized to the range (0, 1). 
    Attempts to replicate matplotlib.imread() without matplotlib.
    Uses "maxgray" in 'params', if available.
    """
    if params is None: params = {}
    imraw = scipy.misc.imread(filename)
    mg = float(params.get('maxgray', 0))
    if not mg: # Guess
        if imraw.dtype.name == 'uint8':
            mg = 2**8 - 1
        elif imraw.dtype.name == 'uint16':
            mg = 2**16 - 1
        elif imraw.dtype.name.startswith('float'):
            mg = 1.0
        else:
            raise ValueError("Can't guess max gray value of image. Use parameter 'maxgray'.")
    return imraw / float(mg)

def merge_groups(feats, merge_cutoff):
    """Post-process a DataFrame to merge features within 'merge_cutoff' of each other.
    
    Sums the values in the 'intensity' column, and sets 'rg2' to NaN.

    Uses a crude algorithm that merges any close neighbors it encounters. This means
    that extended cluters of multiple features may not be completely merged, if a
    feature at the edge of the cluster is examined first.
    """
    xy = feats[['x', 'y']].values
    masses = feats[['intensity']].values
    rg2 = feats[['rg2']].values
    ckdtree = cKDTree(xy, 5)

    for i in range(len(xy)):
        dists, nns = ckdtree.query(xy[i], k=6, distance_upper_bound=merge_cutoff) # Groups of up to 6 features
        if dists[1] < 1e23:
            nnids_all = nns.compress(~np.isinf(dists))
            # Exclude already-processed neighbors, whose rg2's have been nulled.
            nnids = [nn for nn in nnids_all if not np.isnan(rg2[nn])] 
            if len(nnids) > 1:
                xy[i,:] = np.mean(xy[nnids], axis=0)
                masses[i] = np.sum(masses[nnids])
                # It's not clear how to merge rg2. So we use it
                # to mark features as merged, and allow cutting of those rows
                rg2[nnids[1:]] = np.nan 
    feats_merged = feats.copy()
    feats_merged['x'] = xy[:,0]
    feats_merged['y'] = xy[:,1]
    feats_merged['intensity'] = masses
    feats_merged['rg2'] = rg2
    return feats_merged.dropna()

def get_window(winfilename='window.ini'):
    """Returns the contents of 'window.ini' as a dict of integers.

    Indices in window.ini are interpreted ImageJ-style (1-based).

    Caller must be prepared to interpret "-1" as "end"."""
    return interpret_window(readSingleCfg(winfilename))
def interpret_window(windowdict):
    """Fill in missing or special values in a window specification.
    
    This processes the content of "window.ini"."""
    win = dict(xmin=float(windowdict.get('xmin', 1)) - 1, 
            xmax=float(windowdict.get('xmax', -1)) - 1,
            ymin=float(windowdict.get('ymin', 1)) - 1, 
            ymax=float(windowdict.get('ymax', -1)) - 1,
            firstframe=int(windowdict.get('firstframe', 1)), 
            lastframe=int(windowdict.get('lastframe', -1)))
    if win['xmax'] < 0:
        win['xmax'] = np.inf
    if win['ymax'] < 0:
        win['ymax'] = np.inf
    return win
def link_dataframes(points, params):
    """Takes an iterator of (framenumber, DataFrame) tuples. 

    Requires columns 'x', 'y'.
    Returns an iterable of DataFrames, now with 'particle' and 'frame' columns.
    
    See module docs for 'params'
    """
    search_range = float(params.get('maxdisp', None))
    memory = int(params.get('memory', 0))
    def preparePoints(point_datum):
        # Prepare input
        fnum, ftr = point_datum
        ftr = ftr.copy()
        ftr['indx'] = ftr.index.values
        return [trackpy.linking.IndexedPointND(fnum, (x, y), indx) for x, y, indx \
                in ftr[['x', 'y', 'indx']].values.tolist()]
    def unpackTracks(pair):
        # Add tracking output (particle IDs) to full particle data.
        point_data, tracks = pair
        fnum, ftr = point_data
        ftr = ftr.copy()
        ftr['frame'] = fnum
        labels = map(lambda x: x.track.id, tracks)
        ftr['particle'] = pandas.Series(labels, dtype=float)
        return ftr
    point_data, point_data_tolink = itertools.tee(points)
    linkiter = trackpy.linking.link_iter(itertools.imap(preparePoints, point_data_tolink),
                                search_range,
                                memory=memory,
                                neighbor_strategy='KDTree',
                                link_strategy='nonrecursive')
    return itertools.imap(unpackTracks, itertools.izip(point_data, linkiter))
# An entire tracking pipeline, including storage to disk
def track2disk(imgfilenames, outfilename, params, selectframes=None, 
        window=None, progress=False, statusfile=None):
    """Implements a complete tracking process, from image files to a complete
    pytables (HDF5) database on disk.

    Appropriate for large datasets.
    
    'imgfilenames' is the complete list of image files.
    'outfilename' conventionally has the ".h5" extension.
    See module docs for 'params' and 'window'.
    'selectframes' is a list of frame numbers to use, COUNTING FROM 1. Default is all.
    If 'progress', a status message will be displayed in IPython.
    'statusfile' optionally creates a JSON file that is continually updated with status
        information.

    NOTE: track.imread() is used to read the image files. This does not always behave
    as the more familiar imread() in pylab.
    """
    try: # Always close output file
        outfile = None
        if os.path.exists(outfilename): # Check now *and* later
            raise IOError('Output file already exists.')
        filepairs_all = [(i + 1, filename) for i, filename in enumerate(imgfilenames)]
        if selectframes is None:
            filepairs = filepairs_all
        else:
            filepairs = [filepairs_all[i - 1] for i in selectframes]
        if statusfile is not None:
            stopwatch = Stopwatch()
            statfile = StatusFile(statusfile, 
                    dict(totalframes=len(filepairs), outfile=outfilename,
                        working_dir=os.getcwd(), process_id=os.getpid(),
                        started=stopwatch.started))
            statfile.update(dict(status='starting'))
        tracks_iter = link_dataframes(feature_iter(filepairs, params, window=window), 
                params)
        for (fnum, filename), ftr in itertools.izip(filepairs, tracks_iter):
            if statusfile is not None:
                stopwatch.lap()
                statfile.update(dict(status='working', mr_frame=fnum, mr_imgfile='filename',
                    nparticles=len(ftr), seconds_per_frame=stopwatch.mean_lap_time(),
                    elapsed_time=format_td(stopwatch.elapsed()), 
                    time_left=format_td(stopwatch.estimate_completion(len(filepairs)))))
            if progress:
                import IPython.display
                IPython.display.clear_output()
                print '{} particles in frame {} of {}: {}'.format(
                        len(ftr), fnum, len(filepairs), filename)
                sys.stdout.flush()
            if outfile is None:
                # We create the output file now so we can provide an estimate of total size.
                if os.path.exists(outfilename):
                    raise IOError('Output file already exists.')
                outfile = tables.openFile(outfilename, 'w')
                alltracks = outfile.createTable('/', 'bigtracks', TrackPoint,
                        expectedrows=len(ftr) * len(imgfilenames),)
                        #filters=tables.Filters(complevel=5, complib='blosc'))
            alltracks.append(
                ftr[['frame', 'particle', 
                        'x', 'y', 'intensity', 'rg2']].values.astype('float32'))
            alltracks.flush()
        if statusfile is not None:
            statfile.update(dict(status='finishing',
                elapsed_time=format_td(stopwatch.elapsed()),
                seconds_per_frame=stopwatch.mean_lap_time()))
        if outfile is not None:
            _create_table_indices(alltracks)
    finally:
        if outfile is not None:
            outfile.close()
    if statusfile is not None:
        statfile.update(dict(status='done',
            elapsed_time=format_td(stopwatch.elapsed()),
            seconds_per_frame=stopwatch.mean_lap_time()))

# Tracks file indexing
def create_tracksfile_indices(tracksfilename):
    """Create indices for the tracks data in the HDF5 file 'tracksfilename'.
    Indices are necessary to efficiently access the data.

    This is only necessary if the normal tracking process (with track2disk())
    did not finish successfully.
    """
    outfile = tables.openFile(tracksfilename, 'a')
    try:
        trtab = outfile.root.bigtracks
        _create_table_indices(trtab)
    finally:
        outfile.close()
def _create_table_indices(trackstable):
    """Create indices on the tracks PyTables table."""
    trackstable.cols.frame.createIndex()
    trackstable.cols.particle.createIndex()

# Format of the tracks data file
class TrackPoint(tables.IsDescription):
    """pytables format for tracks data"""
    frame = tables.Float32Col(pos=1)
    particle = tables.Float32Col(pos=2)
    x = tables.Float32Col(pos=3)
    y = tables.Float32Col(pos=4)
    intensity = tables.Float32Col(pos=5)
    rg2 = tables.Float32Col(pos=6)

