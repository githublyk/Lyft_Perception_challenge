import os
import sys
import random
import math
import re
import time
import numpy as np
import cv2
import matplotlib
import matplotlib.pyplot as plt
import skimage.io
from imgaug import augmenters as iaa

ROOT_DIR = os.path.abspath("./")


sys.path.append(ROOT_DIR)  # To find local version of the library
sys.path.append(os.path.join(os.getcwd(),"./Mask_RCNN/"))

from mrcnn.config import Config
from mrcnn import utils
import mrcnn.model as modellib
from mrcnn import visualize
from mrcnn.model import log


sys.path.append(os.path.join("./Mask_RCNN/", "samples/coco/"))  # To find local version
import coco

MODEL_DIR = os.path.join('./', "logs")

COCO_MODEL_PATH = os.path.join(ROOT_DIR, "mask_rcnn_coco.h5")
# Download COCO trained weights from Releases if needed
if not os.path.exists(COCO_MODEL_PATH):
    utils.download_trained_weights(COCO_MODEL_PATH)


class LyftChallengeConfig(Config):
    """Configuration for training on the toy shapes dataset.
    Derives from the base Config class and overrides values specific
    to the toy shapes dataset.
    """
    # Give the configuration a recognizable name
    NAME = "shapes"

    # Train on 1 GPU and 8 images per GPU. We can put multiple images on each
    # GPU because the images are small. Batch size is 8 (GPUs * images/GPU).
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1

    # Number of classes (including background)
    NUM_CLASSES = 1 + 2  # background + 2 shapes

    # Use small images for faster training. Set the limits of the small side
    # the large side, and that determines the image shape.
    IMAGE_MIN_DIM = 128
    # IMAGE_MAX_DIM = 128
    IMAGE_MAX_DIM = 1024

    # Use smaller anchors because our image and objects are small
    RPN_ANCHOR_SCALES = (8, 16, 32, 64, 128)  # anchor side in pixels

    # Reduce training ROIs per image because the images are small and have
    # few objects. Aim to allow ROI sampling to pick 33% positive ROIs.
    TRAIN_ROIS_PER_IMAGE = 32

    # Use a small epoch since the data is simple
    STEPS_PER_EPOCH = 100

    # use small validation steps since the epoch is small
    VALIDATION_STEPS = 5
    
config = LyftChallengeConfig()
config.display()





class lyftDataset(utils.Dataset):
    random_idx=0
    def load_images(self,dataset_dir,dataset_type='train'):
        image_paths = os.path.join(dataset_dir,'CameraRGB')
        # image_paths = os.path.join(dataset_dir,'extraRGB')
        images = os.listdir(image_paths)

        self.add_class("shapes", 1, "road")
        self.add_class("shapes", 2, "car")

        if dataset_type=='train':
            images = images[:900]
        elif dataset_type=='val':
            images = images[900:]
        else:
            # images = images[900:]
            raise ValueError("param should be train or val")

        for _image in images:
            # image = skimage.io.imread(os.path.join(image_paths,_image))
            # height, width = image.shape[:2]
            print("[image]",os.path.join(image_paths,_image))  
            self.add_image(
                    "shapes",
                    image_id=_image,  # use file name as a unique image id
                    path=os.path.join(image_paths,_image))
                    # width=width, height=height)          

    def load_image(self, image_id):
        """Load the specified image and return a [H,W,3] Numpy array.
        """
        # Load image
        image = skimage.io.imread(self.image_info[image_id]['path'])
        image = cv2.resize(image,(256,256))
        # If grayscale. Convert to RGB for consistency.
        if image.ndim != 3:
            image = skimage.color.gray2rgb(image)
        # If has an alpha channel, remove it for consistency
        if image.shape[-1] == 4:
            image = image[..., :3]
        # image = cv2.resize(image, dsize=(256, 256), interpolation=cv2.INTER_CUBIC)    
        return image

    def load_mask(self,image_id):
        # print(self.random_idx)
        self.random_idx+=1
        image_info = self.image_info[image_id]
        if image_info["source"] != "shapes":
            print("not shape",image_info["source"])
            return super(self.__class__, self).load_mask(image_id)
        info = self.image_info[image_id]
        mask_label = skimage.io.imread(os.path.join("./Train/CameraSeg",info["id"]))
        # mask_label = skimage.io.imread(os.path.join("./Train/extraSeg",info["id"]))

        mask = self.process_labels(mask_label[:,:,0])
        mask = cv2.resize(mask,(256,256))
        
        return mask,np.array([1,2], dtype=np.int32)

    def process_labels(self,labels):
        
        # labels_new = np.copy(labels)
        labels_new = np.zeros(labels.shape)
        labels_new_car = np.zeros(labels.shape)
        
        lane_line_idx = (labels == 6).nonzero()
        lane_idx = (labels == 7).nonzero()
        car_pixels = (labels == 10).nonzero()

        car_hood_idx = (car_pixels[0] >= 495).nonzero()[0]
        car_hood_pixels = (car_pixels[0][car_hood_idx], \
                       car_pixels[1][car_hood_idx])

        labels_new[lane_line_idx] = 1

        labels_new[lane_idx] = 1

        labels_new_car[car_pixels] = 1
        labels_new_car[car_hood_pixels] = 0

        
        return np.dstack([labels_new,labels_new_car])


    def image_reference(self, image_id):
        """Return the shapes data of the image."""
        info = self.image_info[image_id]
        if info["source"] == "shapes":
            return info["id"]
        else:
            super(self.__class__).image_reference(self, image_id)



RGB_PATH = 'Train/'

dataset_train = lyftDataset()
dataset_train.load_images(RGB_PATH,dataset_type='train')
dataset_train.prepare()

dataset_val = lyftDataset()
dataset_val.load_images(RGB_PATH,dataset_type='val')
dataset_val.prepare()

# dataset_test = lyftDataset()
# dataset_test.load_images(RGB_PATH,dataset_type='test')
# dataset_test.prepare()
augmentation = iaa.SomeOf((0, None), [
        iaa.Fliplr(0.5),
        iaa.Flipud(0.5),
        iaa.OneOf([iaa.Affine(rotate=90),
                   iaa.Affine(rotate=180),
                   iaa.Affine(rotate=270)]),
        iaa.Multiply((0.8, 1.5)),
        iaa.GaussianBlur(sigma=(0.0, 5.0)),
        # iaa.PiecewiseAffine(scale=(0.01, 0.05)),
        iaa.Affine(scale=(0.5, 1.5)),
        iaa.Affine(scale={"x": (0.5, 1.5), "y": (0.5, 1.5)}),
        # iaa.ElasticTransformation(alpha=(0, 5.0), sigma=0.25)
    ])




model = modellib.MaskRCNN(mode="training", config=config,
                          model_dir=MODEL_DIR)

# model.load_weights(COCO_MODEL_PATH, by_name=True,
#                        exclude=["mrcnn_class_logits", "mrcnn_bbox_fc", 
#                                 "mrcnn_bbox", "mrcnn_mask"])

# model_path = os.path.join('./', "mask_rcnn_lyft.h5")
model_path = os.path.join('./', "mask_rcnn_lyft.h5")
# model_path = model.find_last()[1]

# Load trained weights (fill in path to trained weights here)
assert model_path != "", "Provide path to trained weights"
print("Loading weights from ", model_path)
model.load_weights(model_path, by_name=True)


print("Training ...")
# print(model.get_trainable_layers())
# exit()

# model.train(dataset_train, dataset_val, 
#             learning_rate=config.LEARNING_RATE, 
#             epochs=20,
#             augmentation=augmentation, 
#             layers='heads')

# model.train(dataset_train, dataset_val, 
#             learning_rate=config.LEARNING_RATE / 100.0,
#             epochs=10,
#             augmentation=augmentation, 
#             layers="just_mrcnn_mask")

# model.train(dataset_train, dataset_val, 
#             learning_rate=config.LEARNING_RATE ,
#             epochs=20,
#             augmentation=augmentation, 
#             layers="heads")

model.train(dataset_train, dataset_val, 
            learning_rate=config.LEARNING_RATE/10.0,
            epochs=30,
            augmentation=augmentation, 
            layers="all")

model_path = os.path.join(ROOT_DIR, "mask_rcnn_lyft.h5")
model.keras_model.save_weights(model_path)



# inference

class InferenceConfig(LyftChallengeConfig):
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1

inference_config = InferenceConfig()

# Recreate the model in inference mode
model = modellib.MaskRCNN(mode="inference", 
                          config=inference_config,
                          model_dir=MODEL_DIR)

# Get path to saved weights
# Either set a specific path or find last trained weights
# model_path = os.path.join(ROOT_DIR, ".h5 file name here")


# # Test on a random image

RED = (255,0,0)
GREEN = (0,255,0)
BLUE = (0,0,255)
colors = [RED,GREEN,BLUE]


def segment_images(original_image):
    results = model.detect([original_image], verbose=0)
    r = results[0]
    f_mask = r['masks']
    f_class = r["class_ids"]
    

    no_ch = f_mask.shape[2]
    final_img = np.copy(original_image)
    for ch in range(no_ch):

        _id = f_class[ch]
        if _id==1: 
            color_id=0
        else:
            color_id=1
        print('id:',_id)
        mask_1 = f_mask[:,:,ch]
        mask1 = np.dstack([mask_1*colors[color_id][0],
                            mask_1*colors[color_id][1],
                            mask_1*colors[color_id][2]])
        final_img = cv2.addWeighted(final_img, 1, mask1.astype(np.uint8), 1, 0)
    return final_img

# for image_id in range(900,1000): 

#     original_image = cv2.imread('./Train/CameraRGB/{}.png'.format(image_id))[:,:,::-1]
   
#     final_img = segment_images(original_image)

#     cv2.imshow('output', final_img[:,:,::-1])
#     cv2.waitKey(1)

exit()