## Scripts written for my W2026 rotation in Deku Lab

### Installation
Navigate to the directory where you wish to install the scripts (e.g., ~/src) and run the following commands:
```
git clone https://github.com/ramzymulla/deku_lab_rotation.git
cd deku_lab_rotation
conda env create -n stim_analysis -f stim_analysis.yaml
```

Make sure to update studyparams.py with the necessary information (filepaths, electrode configurations, etc.) prior to using! Data should be organized into folders named "\<subject\>_data" containing the ephys data recorded with Intan RHX, and "\<subject\>_stim_logs" containing the stimulus log file(s) (.csv) written by individual_channel_stim.py during your experiment

