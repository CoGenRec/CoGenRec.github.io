"""Shared capture settings for the official-checkpoint visualization cache."""

from export_selected_scenes import REPO

RUN = REPO / 'output/real_tmrec_offical_weights_and_retrain_weights_three_variants'
METHOD = '001_Ours_with_exposure_augmentation'
AOPS = [0, 4, 8, 12, 16, 20, 24]
RATIO = 25
SOURCE_FPS = 757
