import argparse
import random
import threading
import sys
import cv2
import pyfaceswap
import numpy as np
from ailabs.jarvis import Processor
from PIL import Image

class FsProcessor(Processor):

    def __init__(self):
        super(FsProcessor, self).__init__()

    def on_start(self, session_id):
        print ">>> Processor [Video dummy: metadata] started: %d <<<" % (session_id, )
        self.counter = 0
        self.lastFrame = None
        self.firstFrame = True

    def on_end(self, session_id):
        print ">>> Processor ended: %d <<<" % (session_id, )

    def pil2cv(self, img):
        cvImg = np.array(img)
        cvImg = cv2.cvtColor(cvImg, cv2.COLOR_RGB2BGR)
        return cvImg


    def on_image_frame(self, session_id, stream_id, time, image_frame, metadata):        

        global g_producerSem, g_resImg, g_tgtImg, g_producerEvent, g_consumerEvent, g_bypass

        if self.firstFrame:
            self.lastFrame = (image_frame, metadata)
            self.firstFrame = False

        if self.counter > skipped:
            self.counter = 0

        #Convert image from PIL to ndarray
        cvTgtImage = self.pil2cv(image_frame)
        tgtRszRatio = targetHeight / cvTgtImage.shape[0]

        g_producerSem.acquire()
        g_tgtImg = cv2.resize(cvTgtImage, None, None, fx=tgtRszRatio, fy=tgtRszRatio,\
                interpolation=cv2.INTER_LINEAR)
        if self.counter == 0:
            g_bypass = False
        else:
            g_bypass = True
        g_consumerEvent.set()
        g_producerEvent.wait()
        result = g_resImg
        failed = g_failed
        g_producerEvent.clear()
        g_producerSem.release()

        if not failed:
            rszRes = cv2.resize(result, image_frame.size, interpolation=cv2.INTER_LINEAR)
            rszRes = cv2.cvtColor(rszRes, cv2.COLOR_BGR2RGB)
            print '>>> Image sent'
            self.counter = self.counter + 1
            self.lastFrame = (Image.fromarray(rszRes), metadata)
        else:
            self.counter = 0
        self.send_image_frame(self.lastFrame[0], self.lastFrame[1])


class Renderer(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):

        global g_producerSem, g_resImg, g_tgtImg, g_producerEvent, g_consumerEvent, g_failed

        self.pfs = pyfaceswap.PyFaceSwap()

        self.pfs.loadModels(landmarks, model_3dmm_h5, model_3dmm_dat, reg_model, reg_deploy,\
                reg_mean, seg_model, seg_deploy, genericFace, expReg, highQual, gpuId)

        sourceImg = cv2.imread(source)
        srcRszRatio = targetHeight / sourceImg.shape[0]
        rszSrcImg = cv2.resize(sourceImg, None, None, fx=srcRszRatio, fy=srcRszRatio,\
                interpolation=cv2.INTER_LINEAR)
        if ( self.pfs.setSourceImg(rszSrcImg) ):
            print 'Set Source Image Failed!'
        print '>>> Source set!'


        self.renderer = pyfaceswap.PyFaceRenderer()
        if( self.renderer.createCtx(len(sys.argv), sys.argv) ):
            print 'Initialization failed!'

        fs = self.pfs.getFs()

        while True:
            ## Wait for lock
            print 'Waiting for Rendering...'
            g_consumerEvent.wait()

            ## Render
            print 'Got something to render...'
            if ( not self.pfs.setTargetImg(g_tgtImg, g_bypass) ):
                g_failed = False
                print '>>> Target set!'
                unblended = self.renderer.swap(fs)
                g_resImg = self.pfs.blend(unblended)
            else:
                g_failed = True
            g_producerEvent.set()

            ## Release lock
            print 'Done'
            g_consumerEvent.clear()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--gpu', type=int, required=True)
    parser.add_argument('--highQual', type=int, required=True)
    args = parser.parse_args()

    landmarks = '/root/face_swap/data/models/shape_predictor_68_face_landmarks.dat'       # path to landmarks model file
    model_3dmm_h5 = '/root/face_swap/data/models/BaselFaceModel_mod_wForehead_noEars.h5'  # path to 3DMM file (.h5)
    model_3dmm_dat = '/root/face_swap/data/models/BaselFace.dat'                          # path to 3DMM file (.dat)
    reg_model = '/root/face_swap/data/models/3dmm_cnn_resnet_101.caffemodel'              # path to 3DMM regression CNN model file (.caffemodel)
    reg_deploy = '/root/face_swap/data/models/3dmm_cnn_resnet_101_deploy.prototxt'        # path to 3DMM regression CNN deploy file (.prototxt)
    reg_mean = '/root/face_swap/data/models/3dmm_cnn_resnet_101_mean.binaryproto'         # path to 3DMM regression CNN mean file (.binaryproto)
    seg_model = '/root/face_swap/data/models/face_seg_fcn8s.caffemodel'                   # path to face segmentation CNN model file (.caffemodel)
    seg_deploy = '/root/face_swap/data/models/face_seg_fcn8s_deploy.prototxt'             # path to face segmentation CNN deploy file (.prototxt)
    source = '/root/face_swap/data/images/brad_pitt_01.jpg'     # source image

    # Five global variables for synchronization
    g_failed = False
    g_tgtImg = None
    g_resImg = None
    g_bypass = False
    g_producerSem = threading.Semaphore()
    g_producerEvent = threading.Event()
    g_consumerEvent = threading.Event()

    gpuId = args.gpu
    expReg = 1
    genericFace = 0
    highQual = args.highQual
    if highQual:
        print 'High Quality Enabled!'
        targetHeight = 360.0
        skipped = 0
    else:
        print 'Low Quality Enabled!'
        targetHeight = 180.0
        skipped = 3


    renderThread = Renderer()
    renderThread.start()
    FsProcessor.startToListen(args.port)

