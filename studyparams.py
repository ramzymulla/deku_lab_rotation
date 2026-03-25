import os
import numpy as np

STUDY_NAME = 'HybridDevice'


SUBJECTS = ['FD005','FD006', 'OHSU2']
DATES = {
    'FD005' :   '260304',
    'FD006' :   '260311',
    'OHSU2' :   '260320'
}
DATA_PATH = os.path.join(os.path.expanduser('~'),'Research','dekulab','HybridDevice')
OUTPUT_PATH = os.path.join(os.path.expanduser('~'),'Desktop','dekulab_analysis')

nonStimEdata = {
    'FD006':{
        'lidocaine1'    :   '183148',
        'lidocaine2'    :   '184549',
        'whisk1'        :   '190312'
    },
    'OHSU2':{
        'whisk'         :   '190625'
    }
    
}

nonStimBdata={
    'FD006':{
        'whisk1'        : [[31,41],[80,90]]
    },
    'OHSU2':{
        'whisk'         : []
    }
    
}

edataToUse = {
    'FD006':{
        'main'     :   ('160803','182402')   # original insertion
        # 'site2'     :   ''
    },
    'OHSU2':{
        'main'     :   ('191608','200328')
    }
}

bdataToUse = {
    'FD006':{
        'main'     :   '160754',   # original insertion
        # 'site2'    
    },
    'OHSU2':{
        'main'      :   '191559'
    }

}

SITE_TIP_DEPTHS = {
    'FD006':{
        'main': 2100,
        'site2': 2600
    },
    'FD005':{
        'main': 2100
    },
    'OHSU2':{
        'main':2100
    }
    
}

SHANK_ORDER = np.array([24, 0, 7, 31, 25, 1, 6, 30, 26, 2, 5, 29, 27, 3, 4, 28])
SHANK_DEPTHS = {subject:{site:(SITE_TIP_DEPTHS[subject][site]-500) - np.arange(0,16)*100 for site in SITE_TIP_DEPTHS[subject]} for subject in SUBJECTS}# um
SHANK_CHANS = [f"a-{site:03d}" for site in SHANK_ORDER] 

DONUT_ORDER = np.array([[20, 22, 10, 11, 19, 18, 14, 12],
                [ 8, 23,  9, 21, 13, 17, 15, 16]])

DONUT_CHANS = [[f"a-{site:03d}" for site in row] for row in DONUT_ORDER]

LFP_BANDS = {
            'Delta': (1.5, 4.0),
            'Theta': (4.0, 8.0),
            'Alpha': (8.0, 13.0),
            'Beta': (13.0, 30.0),
            'Low_Gamma': (30.0, 60.0),
            'High_Gamma': (60.0, 100.0),
            'HFO': (100.0, 200.0) 
        }

LAYERS = ['deep','granule','superficial']

