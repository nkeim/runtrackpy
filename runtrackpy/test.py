import os.path, tempfile, shutil, itertools
from glob import glob
import random
import numpy as np
import numpy.random as npr
import scipy.misc

from . import track
from pantracks import BigTracks, bigtracks

def fake_image(motion_seed=1, pos_seed=314, size=200, maxdisp=3):
    """Generate a fake frame of "particles" spaced at least 20 px apart,
    and moved by up to 'maxdisp' away from their mean positions.

    Update 'motion_seed' for each frame to get new displacements.

    Returns (x coordinates, y coordinates, image array)
    """
    # Based on Tom Caswell's test_iden()
    pad = 40
    random.seed(pos_seed)
    X = range(10, size, 20)
    Y = range(10, size, 20)
    random.shuffle(X)
    random.shuffle(Y)
    pos = np.vstack([X, Y])

    np.random.seed(motion_seed)
    pos = pos + (np.random.random(pos.shape) - 0.5) * 2 * maxdisp + pad/2
    return pos[1], pos[0], gen_fake_data(pos, 5, 2.5, (size + pad, size + pad))
def gen_fake_data(list_of_locs, p_rad, hwhm, img_shape):
    """
    Function to generate fake images for testing purposes
    """
    img = np.zeros(img_shape)

    def pixel_values(window, loc):
        i = np.mgrid[window] - loc.reshape(len(window), *[1] * len(window))
        r = np.zeros(i[0].shape)
        for _ in i:
            r += _ ** 2

        return np.exp(-r / (hwhm ** 2))

    for loc in itertools.izip(*list_of_locs):
        window = [slice(int(p) - (p_rad + 2), int(p) + (p_rad + 2) + 1) for p in loc]

        p = pixel_values(window, np.array(loc))
        img[window] += p

    img *= 5
    img += npr.randn(*img.shape) * .1

    return img

def test_identification():
    x, y, img = fake_image(1, maxdisp=3)
    params = dict(featsize=4, bphigh=1, threshold=0.3)
    ftr = track.identify_frame((img.max() - img) / img.max(), params)
    assert np.max(np.abs(ftr.y - np.array(sorted(y)))) < 0.1

class test_pipeline():
    # i.e. track2disk
    def setUp(self):
        self.params = dict(bright=1, featsize=5, bphigh=2, threshold=0.5, maxdisp=3 * np.sqrt(8))
        self.testdir = tempfile.mkdtemp()
        self.extension = 'PNG'
        self.outputfile = os.path.join(self.testdir, 'bttest_tracks.h5')
        self.nframes = 3
        for framenumber in range(self.nframes):
            x, y, img = fake_image(framenumber)
            self.nparticles = len(x)
            scipy.misc.imsave(os.path.join(self.testdir, 
                'bttest_%.4i.%s' % (framenumber, self.extension)), img)
    def test_tracking(self):
        imgfiles = glob(os.path.join(self.testdir, '*.' + self.extension))
        track.track2disk(imgfiles, self.outputfile, self.params)
        bt = BigTracks(self.outputfile)
        assert bt.maxframe() == self.nframes
        assert len(bt.get_all()) == self.nframes * self.nparticles
        assert bt[1].frame.values[0] == 1.0
        btq = bigtracks.compute_quality(bt, frame_interval=1)
        assert btq.Nconserved.values[-1] == self.nparticles
    def tearDown(self):
        shutil.rmtree(self.testdir)

class test_pipeline_predict(test_pipeline):
    def setUp(self):
        test_pipeline.setUp(self)
        self.params['predict'] = 'nearest'
        self.params['maxdisp'] = 4 * np.sqrt(8) # Prediction is bad for fake Brownian particles!

