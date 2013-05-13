"""Support functions for communicating and reading tracking process status."""
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
import numpy as np
import pandas

# Better versions of the next two functions are in TrackingRunner
def read_statuses(statfilenames):
    """Returns DataFrame of status info for a list of filenames"""
    info = []
    for sfn in statfilenames:
        try:
            sf = open(sfn, 'r')
            sfinfo = json.load(sf)
            sfinfo['since_update'] = format_td(datetime.timedelta(0, 
                time.time() - os.path.getmtime(sfn)))
        except IOError:
            sfinfo = {'working_dir': os.path.dirname(os.path.abspath(sfn)),
                    'status': 'waiting'}
        info.append(sfinfo)
    return pandas.DataFrame(info)
def status_board(statfilenames):
    """Presents status info for a list of filenames.

    Returns a DataFrame, which should display nicely.
    """
    df = read_statuses(statfilenames)
    columns = ['working_dir', 'outfile', 'process_id',
            'totalframes', 'seconds_per_frame', 'elapsed_time', 'time_left', 'status',
            'since_update']
    for cn in columns:
        if cn not in df:
            df[cn] = ''
    return df[columns]

# Support for communicating tracking status from a worker process
class StatusFile(object):
    """JSON-formatted file for monitoring status of a long-running computation"""
    def __init__(self, filename, persistent_info):
        """'persistent_info' will be included in every update."""
        self.filename = filename
        self.persistent_info = persistent_info.copy()
    def update(self, newinfo):
        """Write status file with 'newinfo', including persistent information."""
        tmpname = self.filename + '._tmp'
        tmpfile = open(tmpname, 'w')
        info = self.persistent_info.copy()
        info.update(newinfo)
        json.dump(info, tmpfile, indent=4, separators=(',', ': '))
        tmpfile.close()
        if os.name == 'nt':
            os.unlink(self.filename) # Windows doesn't allow overwriting existing file
        os.rename(tmpname, self.filename)

class Stopwatch(object):
    """Keeps track of execution time"""
    def __init__(self):
        """Start the stopwatch"""
        self.timestamp_start = datetime.datetime.now()
        self.started = self.timestamp_start.strftime('%c')
        self.laptimes = []
    def lap(self):
        """Mark completion of a lap (or cycle, etc.)"""
        self.laptimes.append(datetime.datetime.now())
    def elapsed(self):
        """Returns datetime.timedelta instance of time since start.
        
        The result looks nice when converted to a string.
        """
        return datetime.datetime.now() - self.timestamp_start
    def mean_lap_time(self):
        """Mean time, in seconds, between laps"""
        if not self.laptimes:
            return np.nan
        return (self.laptimes[-1] - self.timestamp_start).total_seconds() \
                / float(len(self.laptimes))
    def estimate_completion(self, total_laps):
        """Estimate how much time is left until completion.

        Specify expected total number of laps.
        
        Returns datetime.timedelta, which can be converted to a string.
        Returns 'None' if time would be negative.
        """
        nlaps = len(self.laptimes)
        if nlaps > total_laps:
            return None
        return datetime.timedelta(0, 
                self.mean_lap_time() * (total_laps - len(self.laptimes)))

def format_td(timedelt):
    """Format a timedelta object as NNhNNmNNs"""
    s = int(round(timedelt.total_seconds()))
    hours = s // 3600
    minutes = (s % 3600) // 60
    seconds = (s % 60)
    return '{:02d}:{:02d}:{:02d}'.format(hours, minutes, seconds)
