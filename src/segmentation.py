import numpy as np
import SimpleITK as sitk
from registration import LinearTransform, NonLinearTransform
import utils as ut

NEW_PATH = "../data/resampled_images_256/"
CMN_IMG_PATH = NEW_PATH + "{}_image.nii"
CMN_MASK_PATH = NEW_PATH + "{}_mask.nii"

GRP_IMG_PATH = NEW_PATH + "{}_image.nii"
GRP_MASK_PATH = NEW_PATH + "{}_mask.nii"

# CMN_IMG_PATH  = "../data/COMMON_images_masks/common_{}_image.nii"
# CMN_MASK_PATH = "../data/COMMON_images_masks/common_{}_mask.nii"
# GRP_IMG_PATH  = "../data/g3_{}_image.nii"
# GRP_MASK_PATH = "../data/g3_{}_mask.nii"

class AtlasSegmentation():
    def __init__(self):
        grp_indices = [59, 60, 61]
        cmn_indices = [40, 41, 42]
        
        self.cmn_img, self.grp_img = {}, {}
        self.cmn_mask, self.grp_mask = {}, {}

        self.cmn_img_data, self.grp_img_data = {}, {}
        self.cmn_mask_data, self.grp_mask_data = {}, {}

        for i in range(len(cmn_indices)):
            
            self.cmn_img[cmn_indices[i]] = sitk.ReadImage(
                CMN_IMG_PATH.format(cmn_indices[i]))
            self.cmn_img_data[cmn_indices[i]] = sitk.GetArrayFromImage(
                self.cmn_img[cmn_indices[i]])

            self.cmn_mask[cmn_indices[i]] = sitk.ReadImage(
                CMN_MASK_PATH.format(cmn_indices[i]))
            self.cmn_mask_data[cmn_indices[i]] = sitk.GetArrayFromImage(
                self.cmn_mask[cmn_indices[i]])

            self.grp_img[grp_indices[i]] = sitk.ReadImage(
                GRP_IMG_PATH.format(grp_indices[i]))
            self.grp_img_data[grp_indices[i]] = sitk.GetArrayFromImage(
                self.grp_img[grp_indices[i]])

            self.grp_mask[grp_indices[i]] = sitk.ReadImage(
                GRP_MASK_PATH.format(grp_indices[i]))
            self.grp_mask_data[grp_indices[i]] = sitk.GetArrayFromImage(
                self.grp_mask[grp_indices[i]])

    def majority_voting(self, reg_masks):
        """Provide the majority voting result for a list of segmented images. The images must be nd-arrays"""

        _, height, width = reg_masks[0].shape
        depth = min([reg_mask.shape[0] for reg_mask in reg_masks])

        min_reg_masks = [reg_mask[:depth, :, :] for reg_mask in reg_masks]
        #labels = np.unique(reg_masks[0][:depth, :, :]) # double check
        labels = [1, 2]
        result = np.zeros((depth, height, width))
        
        for label in labels:
            majority_class = []
            for i, reg_mask in enumerate(min_reg_masks):
                majority_class.append(np.ndarray.flatten(reg_mask))
                majority_class[i][majority_class[i] != label] = 0
                majority_class[i][majority_class[i] == label] = 1

            majority_class = np.array(majority_class)
            majority_class = np.sum(majority_class, axis=0)
            
            majority_class[majority_class < 2] = 0
            majority_class[majority_class > 0] = label
            majority_class = majority_class.reshape([depth, height, width])
            result[majority_class==label] = label

        return result

    def seg_atlas(self, id_cmn):
        """ Apply atlas-based segmentation of `self.cmn_img[id_cmn]` using the list of CT images in `self.grp_img_data` and
        the corresponding segmentation masks in `self.grp_mask_data`. 
        Return the resulting segmentation mask after majority voting. """

        image = self.cmn_img[id_cmn]
        foreground_mask = image > 0
        reg_masks = []

        for id_grp in self.grp_img:
            # compute linear affine transformation with MI
            lin_trf = LinearTransform(
                im_ref=image, im_mov=self.grp_img[id_grp])
            lin_xfm = lin_trf.est_transf(metric="MI", num_iter=200, fix_img_mask=foreground_mask) #, mov_img_mask=self.grp_mask[id_grp], fix_img_mask=self.cmn_mask[id_cmn]
            # apply it to group image and its mask 
            lin_reg_img  = sitk.Resample(self.grp_img[id_grp], image, lin_xfm, sitk.sitkLinear, 0.0,
                                        self.grp_img[id_grp].GetPixelID())
            lin_reg_mask = sitk.Resample(self.grp_mask[id_grp], image, lin_xfm, sitk.sitkNearestNeighbor, 0.0,
                                        self.grp_mask[id_grp].GetPixelID())
            # compute FFD transform
            nl_trf = NonLinearTransform(
                im_ref=image, im_mov=lin_reg_img)
            nl_xfm = nl_trf.est_transf(metric="SSD", num_iter=10 ,  fix_img_mask=foreground_mask)#  fix_img_mask=self.cmn_mask[id_cmn]
            # apply it to linearly trasformed mask 
            nl_reg_mask = sitk.Resample(lin_reg_mask, image,nl_xfm, sitk.sitkLinear, 0.0, lin_reg_mask.GetPixelID())

            reg_masks.append(sitk.GetArrayFromImage(nl_reg_mask))

        cmn_img = ut.read_image(CMN_IMG_PATH.format(id_cmn))

        for mask in reg_masks:
            ut.plot_3d_img_masked(cmn_img, sitk.GetImageFromArray(mask))
            
        return self.majority_voting(reg_masks)


def dice_analysis(mask, ref_mask):
    """Checking and fixing Origin and Spacing, Maybe this is not how this should be fixed. """
    if mask.GetSpacing() != ref_mask.GetSpacing():
        ref_mask.SetSpacing(mask.GetSpacing())

    if mask.GetOrigin() != ref_mask.GetOrigin():
        ref_mask.SetOrigin(mask.GetOrigin())

    overlap_measures_filter = sitk.LabelOverlapMeasuresImageFilter()
    overlap_measures_filter.Execute(ref_mask, mask)
    result = overlap_measures_filter.GetDiceCoefficient()
    return result


def hausdorf_distance_analysis(mask, ref_mask):
    """Checking and fixing Origin and Spacing, Maybe this is not how this should be fixed. """
    if mask.GetSpacing() != ref_mask.GetSpacing():
        ref_mask.SetSpacing(mask.GetSpacing())

    if mask.GetOrigin() != ref_mask.GetOrigin():
        ref_mask.SetOrigin(mask.GetOrigin())

    hausdorff_distance_filter = sitk.HausdorffDistanceImageFilter()

    hausdorff_distance_filter.Execute(ref_mask, mask)
    result = hausdorff_distance_filter.GetHausdorffDistance()
    # print(result)
    return result
