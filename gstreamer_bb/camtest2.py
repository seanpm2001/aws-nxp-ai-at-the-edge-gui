import common_util.overlays as overlays
import common_util.gstreamer_video_pipeline as gst_pipeline
import common_util.colors as colors
import argparse
import gc
import sys

# images
from PIL import Image
from io import BytesIO
import io
import base64
import pickle
from pprint import pprint

import os
import mxnet as mx
import warnings
from mxnet import gluon
from mxnet import nd
from gluoncv.data.transforms import image as timage
from gluoncv import data
import pickle
import time
import array as arr
from queue import Queue
import requests

if (sys.version_info[0] < 3):
    sys.exit("This sample requires Python 3. Please install Python 3!")

# ------------------------------------------------------------------ INFERENCE
class_names =['shell','elbow','penne','tortellini']

warnings.simplefilter("ignore")

ctx = mx.cpu()
net = gluon.nn.SymbolBlock.imports("pasta_inference-symbol.json",['data'], "pasta_inference-0000.params", ctx=ctx)

history = Queue(1000)

class result:
    def __init__(self, score, object,xmin,ymin,xmax,ymax,time):
        self.score = score
        self.object = object
        self.xmin = xmin
        self.ymin = ymin
        self.xmax = xmax
        self.ymax = ymax
        self.time = time
    def json(self):
        return ('{"score": "%s","object": "%s","xmin": "%s","ymin": "%s","xmax": "%s","ymax": "%s"}'
                    %(self.score,self.object,self.xmin,self.ymin,self.xmax,self.ymax))

class inference:
    def __init__(self, timestamp, inference_time,results):
        self.timestamp = timestamp
        self.inference_time = inference_time
        self.results = results
    def json(self):
        results = ('{"timestamp": "%s","inference_time": "%s",'
                    %(self.timestamp,self.inference_time))
        results = results + '"last":['
        for i in range(len(self.results)):
            results = results + self.results[i].json()
            if(i<len(self.results)-1):
                results = results + ','
        results = results +']}'
        return results

last_inference = inference(0,0,[])

def get_inference(input_image):
    global last_inference


    frame = mx.nd.array(input_image).astype('uint8')
    img, frame = timage.presets.ssd.transform_test(frame, short=240, max_size=1024)
    #img = timage.resize_short_within(img, 240, 1024)
    #orig_img = img.asnumpy().astype('uint8')
    #img = mx.nd.image.to_tensor(img)
    #img = mx.nd.image.normalize(img, mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))

    # do the inference and get the time to delta
    t1= time.time()
    objects, scores, bounding_boxes = net(img)
    #objects, scores, bounding_boxes = net(img.expand_dims(0))
    # we need this to sync the inference
    nd.waitall()
    t2= time.time()

    i=0
    result_set=[]

    # only put on the list the detection with score higher than 0.4
    while (scores[0][i].asscalar() >= 0.4) :

        if int(objects[0][i].asscalar()) <= 3:
            this_object=class_names[int(objects[0][i].asscalar())]
            
            this_result = result(
                        score= scores[0][i].asscalar(),
                        object= this_object,
                        xmin= bounding_boxes[0][i][0].asscalar(),
                        ymin= bounding_boxes[0][i][1].asscalar(),
                        xmax= bounding_boxes[0][i][2].asscalar(),
                        ymax= bounding_boxes[0][i][3].asscalar(),
                        time= t2-t1)
            result_set.append(this_result)

        i=i+1

    last_inference = inference(t2,t2-t1,result_set)
    history.put(last_inference, block=True, timeout=None)

    return result_set
# ------------------------------------------------------------------ END INFERENCE

def color_by_id(id):
    """Returns a somewhat-unique color for the given class ID"""
    return [c / 255 for c in colors.COLORS[id % len(colors.COLORS)]]


def main():
    print("Calling video and inference")

    with gst_pipeline.VideoOverlayPipeline(
            "Pasta demo",
            "/dev/video4") as pipeline:

        while pipeline.running:
            # Get a frame of video from the pipeline.
            frame = pipeline.get_frame()
            if frame is None:
                print("Frame is none ...")
                break

            # call the inference method and made delta time
            t1= time.time()
            ret = get_inference(frame.data)
            t2= time.time()
            #print("After get_inference " + str(t2 -t1))

            #requests.get("http://localhost:5002/cb/speed/100")
            #time.sleep(0.4)
            #requests.get("http://localhost:5002/cb/speed/0") 
            #ret = get_inference(frame.data)

            pipeline.clear_overlay()
            pipeline.add_overlay(overlays.Text("Pasta Detection", x=0, y=0,
                                              bg_color=color_by_id(-1)))

            # for each item detected
            for item in ret:
                bbox = overlays.BoundingBox(
                    (item.xmin)/320,
                    (item.ymin)/240,
                    (item.xmax - item.xmin)/320,
                    (item.ymax - item.ymin)/240,
                    item.object,
                    bg_color=color_by_id(5))
                pipeline.add_overlay(bbox)
                #print("Detected: " + item.object)
                #print(item.score)
                #print(item.time)

            print('OVER\t' + str(time.time()))
            pipeline._buffer = frame.data
            #pipeline._overlay.emit('draw', pipeline._cr, time.time(), 0)
            gc.collect()


import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

if (__name__ == "__main__"):
    main()
