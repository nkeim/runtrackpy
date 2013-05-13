import numpy as np
import random
from trackpy import identification

from . import track

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
    return pos[1], pos[0], identification.gen_fake_data(pos, 5, 2.5, (size + pad, size + pad))

def test_identification():
    x, y, img = fake_image(1, maxdisp=3)
    params = dict(featsize=4, bphigh=1, threshold=0.3)
    ftr = track.identify_frame((img.max() - img) / img.max(), params)
    assert np.max(np.abs(ftr.y - np.array(sorted(y)))) < 0.1
