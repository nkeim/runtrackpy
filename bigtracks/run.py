"""Manage tracking of many movies in parallel."""
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

import os, json, time, datetime
import pandas
from util import DirBase, readSingleCfg
from .statusboard import format_td

def _runtracking(mov, cfg, progress=False):
    """Decide parameters for tracking and then run track2disk().

    'cfg' is a dict that can contain tracking parameters in the 'quickparams' entry;
    otherwise, they are loaded from disk.
    
    To be run in a parallel worker. Expects to find the track2disk() function in
    bigtracks.track
    """
    from bigtracks.track import track2disk, get_window
    with mov():
        # Read parameters
        if cfg.get('quickparams') is not None:
            params = cfg['quickparams']
        else:
            params = readSingleCfg(cfg['paramsfilename'])
        # Find image files
        if cfg.get('frames_pattern') is not None:
            framefiles = mov.p.glob(cfg['frames_pattern'])
        else:
            try:
                framefiles = mov.framesRecord().filename.tolist()
            except AttributeError:
                raise RuntimeError('Automatic image filenames not available. Specify "frames_pattern"')
        # Choose frames
        if cfg.get('selectframes') is not None:
            selectframes = cfg['selectframes']
        else:
            window = get_window()
            lastframe = window['lastframe']
            if lastframe == -1: 
                lastframe = len(framefiles)
            selectframes = range(window['firstframe'], lastframe + 1)
        track2disk(framefiles, 
                cfg['tracksfilename'], params, selectframes=selectframes,
                statusfile=cfg['statusfilename'], progress=progress)
    return mov.p
class TrackingRunner(object):
    """User interface for parallel tracking in IPython. Basic idea: run a specified 
    function (default runtracking()) in a parallel worker for each movie directory 
    given, and monitor status of the tracking jobs.

    'movie_dirs' is a list of directory names.
    'load_balanced_view' is an IPython parallel processing view. If not specified, you
        can use only the run() method below. 
    'tracksfilename' is the destination tracks file in each movie directory. 
        By convention it has the extension ".h5". Any needed subdirectories
        will be created.
    'quickparams' lets you pass a dictionary of tracking parameters. 
        If you do not specify it, the tracking parameters are loaded from
        the file "bigtracks.ini" in each movie directory. See the "track" module 
        for details of what parameters are required.
    'frames_pattern' uses glob-style wildcards to specify image files, e.g.
        "Frame_*.png"
    'paramsfilename' is the name of the .ini file in each directory where parameters
        are stored (ignored if 'quickparams' was given).
    'statusfilename' and 'tracking_function' are not user-serviceable.
    
    An instance can be constructed with 'from_objects()' if you would like to pass 
    your own instances of util.DirBase() or some work-alike class.
    """
    # FIXME: Restructure so that self.movies is a collection of task objects. 
    # This would let options like 'quickparams' be set on a per-task basis.
    def __init__(self, movie_dirs, load_balanced_view=None, 
            tracksfilename='bigtracks.h5', 
            quickparams=None, frames_pattern=None,
            paramsfilename='bigtracking.ini',
            statusfilename='trackingstatus.json', 
            tracking_function=_runtracking):
        """If quickparams == None, use 'bigtracks.ini' in each directory.
        If frames_pattern == None, tries to obtain the file list from
            the author's own custom movie class.
        """
        self.movies = [DirBase(d) for d in movie_dirs]
        self.tracksfilename = tracksfilename
        self.statusfilename = statusfilename
        self.paramsfilename = paramsfilename
        self.frames_pattern = frames_pattern
        self.quickparams = quickparams
        self.tracking_function = tracking_function
        self.parallel_results = []
        self.parallel_results_mostrecent = {}
        self.load_balanced_view = load_balanced_view
    @classmethod
    def from_objects(cls, objlist, *args, **kw):
        """Initializes a TrackingRunner from a list of DirBase-like objects"""
        r = cls([], *args, **kw)
        r.movies = objlist
        return r
    def _prepare_run_config(self, mov):
        cfg = dict(quickparams=self.quickparams, tracksfilename=self.tracksfilename,
                statusfilename=self.statusfilename, paramsfilename=self.paramsfilename,
                frames_pattern=self.frames_pattern)
        return mov, cfg
    def submit(self, movie_index, clear_output=False):
        """Submit (or resubmit) a job to the load-balanced view.
        'movie_index' references what you see from status_board().

        If 'clear_output', delete the output and status files.
        """
        mov = self.movies[movie_index]
        if clear_output:
            outputfile = mov.p / self.tracksfilename
            if outputfile.exists():
                outputfile.unlink()
            statusfile = mov.p / self.statusfilename
            if statusfile.exists():
                statusfile.unlink()
        pres = self.load_balanced_view.apply(self.tracking_function, *self._prepare_run_config(mov))
        self.parallel_results.append((movie_index, pres))
        self.parallel_results_mostrecent[movie_index] = pres
        return pres
    def start(self, clear_output=False):
        """Start jobs for all movies on an IPython load-balanced cluster view.
        If 'clear_output', delete the output and status files.
        """
        for i in range(len(self.movies)):
            self.submit(i, clear_output=clear_output)
    def abort(self, movie_index):
        """Cancel job. 'movie_index' references what you see from status_board().
        """
        return self.parallel_results_mostrecent[movie_index].abort()
    def run(self, movie_index, clear_output=False, progress=False):
        """Run job in the current process (not parallel).
        
        If 'progress', display status updates."""
        mov = self.movies[movie_index]
        with mov():
            if clear_output:
                outputfile = mov.p / self.tracksfilename
                if outputfile.exists():
                    outputfile.unlink()
                statusfile = mov.p / self.statusfilename
                if statusfile.exists():
                    statusfile.unlink()
            return self.tracking_function(*self._prepare_run_config(mov),
                    progress=progress)
    def display_outputs(self):
        from IPython.parallel import TimeoutError
        for i in range(len(self.movies)):
            print 'Movie index {}'.format(i)
            try:
                print self.parallel_results_mostrecent[i].display_outputs()
            except TimeoutError:
                pass
    def read_statuses(self):
        """Returns DataFrame of all status info"""
        info = []
        for mov in self.movies:
            sfn = mov.p / self.statusfilename
            try:
                sf = open(sfn, 'r')
                sfinfo = json.load(sf)
                since_update = datetime.timedelta(0, time.time() - os.path.getmtime(sfn))
                sfinfo['since_update'] = format_td(since_update)
            except IOError:
                sfinfo = {'working_dir': os.path.dirname(os.path.abspath(sfn)),
                        'status': 'waiting'}
                since_update = None
            if (mov.p / self.tracksfilename).exists():
                sfinfo['output'] = 'yes'
            else:
                sfinfo['output'] = ''
            if sfinfo['status'] != 'done':
                if since_update is not None:
                    # heartbeat timeout is 10x frame interval, or 5 minutes, 
                    # whichever is greater.
                    heartbeat_timeout = max(float(sfinfo.get('seconds_per_frame', 0)) * 10, 
                            300)
                    if since_update.total_seconds() > heartbeat_timeout:
                        sfinfo['status'] = 'DEAD'
                else:
                    # If there is a tracks file but no status file, act confused.
                    if sfinfo['output']:
                        sfinfo['status'] = '??'
            else:
                # If there's no tracks file, assume the status is from an old run
                if not sfinfo['output']:
                    sfinfo['status'] = 'waiting'
            info.append(sfinfo)
        return pandas.DataFrame(info)
    def status_board(self):
        """Presents status info for a list of filenames.

        Returns a DataFrame, which should display nicely.
        """
        df = self.read_statuses().rename(columns={'seconds_per_frame': 'secs_per_frame'})
        columns = ['working_dir', 'process_id',
                'totalframes', 'mr_frame', 'secs_per_frame', 
                'elapsed_time', 'time_left', 'status', 'output', 
                'since_update']
        for cn in columns:
            if cn not in df:
                df[cn] = ''
        return df[columns]
    def watch(self, interval=5):
        """Regularly updated status board."""
        import IPython.display
        try:
            while True:
                sb = self.status_board()
                IPython.display.clear_output()
                IPython.display.display_html(sb.to_html(na_rep=''), raw=True)
                time.sleep(interval)
        except KeyboardInterrupt:
            IPython.display.clear_output()
            IPython.display.display_html(sb.to_html(na_rep=''), raw=True)
            print 'Last update: ' + datetime.datetime.now().strftime('%c')
            return


