import os

STUDY_NAME = 'HybridDevice'


SUBJECTS = ['FD005','FD006']
DATA_PATH = os.path.join(os.path.expanduser('~'),'Research','DekuLab','HybridDevice')


SHANK_ORDER = [24, 0, 7, 31, 25, 1, 6, 30, 26, 2, 5, 29, 27, 3, 4, 28]
SHANK_CHANS = [f"a-{site:03d}" for site in SHANK_ORDER] 

DONUT_ORDER = [[20,  8],
                [22, 23],
                [10,  9],
                [11, 21],
                [19, 13],
                [18, 17],
                [14, 15],
                [12, 16]]

DONUT_CHANS = [[f"a-{site:03d}" for site in angle] for angle in DONUT_ORDER]