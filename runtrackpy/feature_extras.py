"""Alternate feature-finding functions"""
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

import numpy as np
from scipy import ndimage
from . import identification
from .track import postprocess_features
import pandas

def mixed_donuts(im, params, window=None, diag=False):
    """Perform a hybrid feature identification on a mixture of 2 kinds of particles:
    Small, Gaussian-like particles, and larger donut-like particles (e.g. with a
    bright optical artifact in the center).

    If "diag", return a dict of diagnostic information.
    """
    featsize = int(params['featsize']) # Feature radius in the conventional sense
    threshold = float(params['threshold']) # Minimum pixel intensity for recognition

    # Two-pass filtering
    sm_width = float(params['sm_width']) # Small Gaussian filter width
    lg_radius = float(params['lg_radius']) # Donut radius
    lg_width = float(params['lg_width']) # Donut thickness
    lg_weight = float(params['lg_weight']) # Relative weighting of large convolution
    
    # Initial feature recognition
    peakfind_smooth = 0.5
    peakfind_radius = featsize - 1

    # Subpixel refinement
    hipass = int(params['hipass']) # Get rid of variations in e.g. background intensity
    subpix_lowpass = 0.7 # Smooth things out for subpixel centroid-finding.
    subpix_hipass = featsize - 1 # sharpen for subpixel centroid-finding.

    # Set up filter kernels
    fr = int((lg_radius + lg_width) * 3)
    r = np.sqrt(np.sum(np.mgrid[-fr:fr+1,-fr:fr+1]**2, 0)) # Radius values for kernels

    imfilt_sm = np.exp(-((r / sm_width)**2)) # Gaussian
    imfilt_sm = imfilt_sm / np.abs(np.sum(imfilt_sm)) # Normalize

    imfilt_lg = np.exp(-((r - lg_radius) / lg_width)**2) # Annulus
    imfilt_lg = imfilt_lg / np.abs(np.sum(imfilt_lg)) # Normalize

    #### Start image processing
    # Make image values relative to some local mean intensity
    im = np.asarray(im).astype(float)

    im_uniform = im - ndimage.filters.uniform_filter(im, hipass, mode='nearest', cval=0)
    im_uniform = -im_uniform # Dark particles on bright background

    # Convolve with each of the 2 kernel shapes and then use the strongest
    # signals from each
    imcon_sm = ndimage.filters.convolve(im_uniform, imfilt_sm)
    imcon_lg = ndimage.filters.convolve(im_uniform, imfilt_lg)
    imcon = np.fmax(imcon_sm, imcon_lg * lg_weight)

    # The hybrid image is spikey, but that's a good thing for local maxima.
    # However, some very proximate spurious peaks can be eliminated with a little
    # smoothing.
    img_gaus = ndimage.filters.gaussian_filter(imcon, peakfind_smooth, 
            mode='nearest', cval=0)
    lm = identification.local_max_crop(img_gaus,
            identification.find_local_max(img_gaus, peakfind_radius),
            featsize)

    # Make image lumpier for subpixel code to work. But this badly attenuates
    # large particles, so we'll need to find mass and r2 in another pass.
    img_lastbp = identification.band_pass(-imcon, subpix_hipass, subpix_lowpass)
    pos, m_dummy, r2_dummy = identification.subpixel_centroid(img_lastbp, lm, featsize)

    # Return to the original hybrid image and use that to get masses and r2.
    # The results are only qualitatively useful!
    pos_dummy, m, r2 = identification.subpixel_centroid(imcon - imcon.min(), lm, featsize)

    # The threshold we really must apply is how bright the particle was in 
    # the *original* image. (See next cell)
    pos_dummy, m_original, r2_dummy = identification.subpixel_centroid(im, lm, featsize)

    df_all = pandas.DataFrame({'x': pos[0,:], 'y': pos[1,:], 'intensity': m, 'rg2': r2,
        'm_original': m_original}).dropna().copy()
    # Apply threshold cut
    df = df_all[df_all.m_original >= threshold * np.pi * featsize**2]
    # Apply other cuts and merging
    dfpost = postprocess_features(df, params, window=window)

    if diag:
        diagdict = dict(imfilt_sm=imfilt_sm, imfilt_lg=imfilt_lg, im_uniform=im_uniform,
                imcon_sm=imcon_sm, imcon_lg=imcon_lg, imcon=imcon,
                img_maxes=img_gaus, local_maxes=lm,
                img_lastbp=img_lastbp, 
                )
        return dfpost, diagdict
    else:
        return dfpost
