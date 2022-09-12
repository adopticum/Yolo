# from ast import Load
import yaml
import os,sys
import cv2
import re
import shutil
import torch
import random
import numpy as np
from tqdm import tqdm
from datetime import datetime as dt
from arguments import parse_config
from boliden_utils import LoadImages, non_max_suppression
from boliden_utils import initialize_yolo_model, scale_preds, get_cut_out,visualize_yolo_2D,xyxy2xywh,to_gray,increase_contrast,norm_preds
TIMESTAMP = dt.now().strftime("%Y%m%d_%H%M%S")
class DataExtractor:
    """
    A Class which reads images, detects a certain class, extract prediction cut out, and saves cut out images to folder
    Args:
        model: Yolo model to make prediction.
        class_id: Id from which class to extract bounding boxes from.
        input_folder: Path to floder which might contain subfolders containing images.
        output_folder: Path where output should be stored.
    """
    def __init__(self, model, class_id, input_folder, output_folder):
        self.model = model
        self.class_id = class_id
        self.input_folder = input_folder
        self.output_folder = output_folder
        if isinstance(self.input_folder,str):
            self.input_folder = [self.input_folder]
        self.image_paths = []
        self.get_image_paths()
        self.images_to_extract = len(self.image_paths)
        self.count = 0
    
    def get_image_paths(self):
        """
        Get all image paths from input folder.
        """
        print("Getting image paths from input folder...")
        for input_folder in self.input_folder:
            for root, dirs, files in os.walk(input_folder):
                # print(files)
                for file in files:
                    if file.endswith(".jpg") or file.endswith(".png"):
                        self.image_paths.append(os.path.join(root, file))
    def save_image_to_dir(self,img,auto=False):
        """
        Save image to output folder.
        """
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
        cv2.imwrite(os.path.join(self.output_folder, str(self.count)+".jpg"), img)
        self.count += 1
    def load_img(self, img_path):
        """
        Load image from path.
        """
        return cv2.imread(img_path)

    def extract(self):
        """
        Extract images from input folder.
        """
        print("Extracting images...")
        for image_path in tqdm(self.image_paths):
            img = self.load_img(image_path)
            self.save_image_to_dir(img)
        print("Done extracting images!")

class VerifyPredictions:
    """
    Using a Yolo model display predictions made and select wether to save image with prediction or to only save image and annotate later.
    
    Args:
        model: Yolo Model used to make predicitons.
        data: LoadImages.
        output_folder: Path where output should be stored.
    """
    def __init__(self, model, data, output_folder,count_auto_annotated=0,count_manual_annotated=0,skipped=0):
        self.model = model
        self.names = self.model.names
        self.stride = self.model.stride
        self.data = data
        self.output_folder = output_folder
        self.count_auto_annotated = count_auto_annotated
        self.count_manual_annotated = count_manual_annotated
        self.skipped = skipped
        self.start = self.count_auto_annotated + self.count_manual_annotated + self.skipped
        self.data.start = self.start
        self.auto_name = "autoSchenk"
        self.manual_name = "manualSchenk"
        self.valid_list = ["082","095","1204","1206","1308","1404","1405","1407","1408","1501","1503","1506",
                            "1508","1509","1510","1511","1516","1601","161","1602","162","163","164","1605","165","1606","166","1607","1608","1609","1610",
                            "1611","1612","1613","1614","1615","1617","1619","1623","1625","1625","191","193","195","196","197","198","1910","2103","2104","2105","2106","2108"]
        self.create_output_dirs()
    def create_output_dirs(self):
        """
        Create output directories.
        """
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
        if not os.path.exists(os.path.join(self.output_folder,self.auto_name)):
            os.makedirs(os.path.join(self.output_folder,self.auto_name))
        if not os.path.exists(os.path.join(self.output_folder,self.manual_name)):
            os.makedirs(os.path.join(self.output_folder,self.manual_name))

    def save_image_to_dir(self,img,lbls:list[torch.Tensor],auto=False):
        """
        Save image to output folder.
        """
        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)
        if auto:
            cv2.imwrite(os.path.join(self.output_folder,self.auto_name, str(TIMESTAMP)+"_"+str(self.count_auto_annotated)+".jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            with open(os.path.join(self.output_folder,self.auto_name,str(TIMESTAMP)+"_"+str(self.count_auto_annotated)+".txt"),"w") as f:
                for lbl in lbls:
                    lbl = lbl.cpu().numpy()
                    for l in lbl:
                        x1,y1,x2,y2,conf,cls = l[:6]
                        x,y,w,h = xyxy2xywh((x1,y1,x2,y2))
                        f.write(" ".join(str(i) for i in [int(cls),x,y,w,h])+"\n")
            self.count_auto_annotated += 1
        else:
            cv2.imwrite(os.path.join(self.output_folder,self.manual_name, str(TIMESTAMP)+"_"+str(self.count_manual_annotated)+".jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            self.count_manual_annotated += 1
    def get_input(self):
        """
        Get input key press from user.
        """
        while True:
            key = cv2.waitKey(0)
            if key == ord("y"):
                return True
            elif key == ord("n"):
                return False
            elif key == ord("s"):
                return "skip"
            elif key == ord("q"):
                return "quit"
            else:
                print("Invalid key press, press 'y' to save image or 'n' to not save image labels.")
    def verify(self):
        """
        Verify predictions made by model.
        """

        print("Verifying predictions...")
        pbar = tqdm(total=len(self.data))
        # Set pbar to start at current count
        pbar.update(self.start)
        for path, img, im0s, vid_cap,_ in self.data:
            pbar.update(1)
            # print(im0s.shape)
            img = to_gray(img.transpose(1,2,0))
            img = increase_contrast(img)
            img = img.transpose(2,0,1)
            img = torch.from_numpy(img).to(self.model.device)
            img = img.float()
            img /= 255.0
            if img.ndimension() == 3:
                img = img.unsqueeze(0)
            pred = self.model(img, augment=True)
            pred = non_max_suppression(pred, 0.05, 0.45, classes=None, agnostic=True)
            pred = scale_preds(pred,img0=im0s,img=img)
            winname = "Whole Image"
            cv2.namedWindow(winname)        # Create a named window
            cv2.moveWindow(winname, 40,30)
            cv2.imshow(winname,cv2.resize(im0s,(640,im0s.shape[0]*640//im0s.shape[1])))
            class_string = visualize_yolo_2D(pred,img0=im0s,img=img,names=self.names,wait=False)
            random_show = random.random() < 0.1
            save = self.get_input() #if class_string in self.valid_list or random_show else self.skip_or_false(false_prob=0.2)
            # if class_string not in ["082","095","1204","1206","1308","1404","1405","1407","1408","1501","1503","1506",
            #                                 "1508","1509","1510","1511","1516","1601","161","1602","162","163","164","1605","165","1606","166","1607","1608","1609","1610",
            #                                 "1611","1612","1613","1614","1615","1617","1619","1623","1625","1625","191","193","195","196","197","198","1910","2103","2104","2105","2106","2108"]:
            #     print("Invalid class, skipping image...")
            #     save = False
            if save == "quit":
                print("Stopped @ Auto Annotated: {}. Manual Annotated: {}. Skipped {}".format(self.count_auto_annotated,self.count_manual_annotated,self.skipped))
                exit()
            elif save =="skip":
                self.skipped += 1
                # print(norm_preds(pred,im0s))
                continue
            # print(f"Saving image: {save}")
            pred = norm_preds(pred,im0s)
            self.save_image_to_dir(im0s,pred,save)
        print("Done verifying predictions!")
    def skip_or_false(self,false_prob:float):
        """
        Skip or return false based on probability.
        """
        det = random.random() < false_prob
        return False if det else "skip"
import random_word
RANDOM_WORD = random_word.RandomWords()
class DataSplitter:
    """
    Split data into train, val and test set.
    When completed dataset folder should contain:
    
    1. train/ Folder containing images (jpg) and labels (txt), images and corresponding label has same name.
    2. val/ - || - Val set.
    3. test/ - || - Test set.
    4. data.yaml. Yaml file containing: names: - list name of classes, 
                                        path: - path to dataset folder.
                                        train: - relative path to train folder, 
                                        val: - relative path to train folder, 
                                        test: - relative path to test folder.
                                        nc: - number of classes.
    Args: 
        input_folder: Folder containing images and labels.
        output_folder: Folder to save train, val and test set.
        train: Percentage of data to use for training.
        val: Percentage of data to use for validation.
        test: Percentage of data to use for testing.
    """
    def __init__(self,input_folder:str, output_fldoer:str, train:float,val:float,test:float) -> None:
        assert train+val+test == 1.0, "Train, val and test must add up to 1.0"
        self.batch_name = str(RANDOM_WORD.get_random_word())
        self.input_folder = input_folder
        self.output_folder = output_fldoer
        self.train = train
        self.val = val
        self.test = test
        self.train_folder = os.path.join(self.output_folder,"train")
        self.val_folder = os.path.join(self.output_folder,"val")
        self.test_folder = os.path.join(self.output_folder,"test")
        self.data_yaml = os.path.join(self.output_folder,"data.yaml")
        self.data_paths = []
        self.names = ["0","1","2","3","4","5","6","7","8","9"]
        self.nc = len(self.names)
        # self.create_folders()
        # self.get_paths()
        # self.split_data()
    def create_folders(self,):
        """
        Create train, val and test folders.
        """
        if not os.path.exists(self.output_folder):
            os.mkdir(self.output_folder)
        if not os.path.exists(self.train_folder):
            os.makedirs(self.train_folder)
        if not os.path.exists(self.val_folder):
            os.makedirs(self.val_folder)
        if not os.path.exists(self.test_folder):
            os.makedirs(self.test_folder)
    def get_paths(self):
        """
        Get paths to images and labels. Store them in tuple.
        """
        for file in os.listdir(self.input_folder):
            if file.endswith(".jpg") or file.endswith(".png"):
                img_path = os.path.join(self.input_folder,file)
                label_path = os.path.join(self.input_folder,file.split(".")[0]+".txt")
                self.data_paths.append((img_path,label_path))
    def copy_data(self,paths,folder):
        import time
        """
        Copy data to train, val or test folder.
        """
        print("Copying data to: {}".format(folder))
        for img_path, label_path in paths:
            dest_path = os.path.join(folder,img_path.split("/")[-1].split(".")[0]+"_"+self.batch_name)
            print(dest_path)
            print("Copying: {}".format(img_path))
            shutil.copy(img_path, dest_path+".jpg")
            lbl = np.loadtxt(label_path, delimiter=" ", dtype=np.float32)
            if len(lbl):
                lbl[:,1] = lbl[:,1]
                if len(lbl) and sum(lbl[:,1]>1) >= 1:
                    print("Error: {}".format(img_path))
                np.savetxt(label_path, lbl, fmt="%d %f %f %f %f", delimiter=" ")
            shutil.copy(label_path, dest_path+".txt")
    def reformat_data(self,paths):
        """
        Labels constist of cls,x,y,w,h in txt files. 
        """
    def create_yaml(self):
        """
        Create yaml file containing dataset information.
        """
        data = {"names":self.names,
                "path":self.output_folder,
                "train":os.path.join(self.output_folder,"train"),
                "val":os.path.join(self.output_folder,"val"),
                "test":os.path.join(self.output_folder,"test"),
                "nc":self.nc}
        with open(self.data_yaml, "w") as outfile:
            yaml.dump(data, outfile, default_flow_style=False)
    def shuffle_data(self):
        """
        Shuffle data.
        """
        random.shuffle(self.data_paths)
    def split_data(self):
        """
        Split data into train, val and test set.
        """
        print("Splitting data...")
        train_len = int(len(self.data_paths)*self.train)
        val_len = int(len(self.data_paths)*self.val)
        test_len = int(len(self.data_paths)*self.test)
        train_paths = self.data_paths[:train_len]
        val_paths = self.data_paths[train_len:train_len+val_len]
        test_paths = self.data_paths[train_len+val_len:]
        self.copy_data(train_paths,self.train_folder)
        self.copy_data(val_paths,self.val_folder)
        self.copy_data(test_paths,self.test_folder)
        # self.create_yaml()
        print("Done splitting data!")

        



with torch.no_grad():
    if __name__=="__main__":
        model,imgsz,names = initialize_yolo_model(parse_config()[0])
        data_ext = DataExtractor(None, 1, ["../datasets/Examples/Sequences/","../datasets/SuperAnnotate/SchenkGood"],"../datasets/Examples/Sequence_images_schenk/")
        #print(data_ext.images_to_extract)
        # # #data_ext.extract()
        print(len(data_ext.image_paths))
        data = LoadImages(data_ext.image_paths,auto=False,img_size=imgsz,stride=model.stride)
        print(len(data))
        verify = VerifyPredictions(model,data,"../datasets/Examples/Sequence_verify_schenk/",count_auto_annotated=0,count_manual_annotated=0) # 247 141
        verify.verify()
        # data_splitter = DataSplitter("../datasets/Examples/Sequence_verify/autoV2/","../datasets/YoloFormat/BolidenDigits/",0.9,0.05,0.05)
        # data_splitter.create_folders()
        # data_splitter.get_paths()
        # data_splitter.split_data()
        # # count = 0
        
        # for path, img, im0s, _,_ in tqdm(data):

        #     img = torch.from_numpy(img).to(model.device)
        #     # cv2.imshow("img",cv2.cvtColor(im0s,cv2.COLOR_RGB2BGR))
        #     # cv2.waitKey(0)
        #     img = img.float()/255.0
        #     if img.ndimension() == 3:
        #         img = img.unsqueeze(0)
        #     pred = model(img)
        #     pred = non_max_suppression(pred, 0.25, 0.45, classes=[1], agnostic=False)
        #     pred = scale_preds(pred, im0s, img)
        #     for i, det in enumerate(pred):
        #         if det is not None and len(det):
        #             # det[:, :4] = scale_preds(det[:, :4], im0s.shape)
        #             for *xyxy, conf, cls in reversed(det):
        #                 cut_out = get_cut_out(im0s, xyxy, offset=30)
        #                 cv2.imwrite("../datasets/Examples/Sequence_cut_outs/"+str(count)+".jpg", cv2.cvtColor(cut_out, cv2.COLOR_RGB2BGR))
        #                 count += 1
