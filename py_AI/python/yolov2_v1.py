import posix_ipc
import cv2
import glob
import numpy as np
import time
import os
import mmap

import socket

#setup UIO transform layout

size = 0x1000
offset = 0

mmap_file = os.open('/dev/uio2', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
uio_map = np.frombuffer(mem, np.uint32, size >> 2)
uio_fp = np.frombuffer(mem, np.float32, size >> 2)

uio_map[0] = 1
time.sleep(0.1)
uio_map[0] = 0
uio_map[1] = 32
uio_map[2] = 416
uio_map[3] = 416

uio_fp[16] = 1.0
uio_fp[17] = 1.0
uio_fp[18] = 1.0
uio_fp[32] = -103.94
uio_fp[33] = -116.78
uio_fp[34] = -123.68

#Get Images

# Specify the directory containing the BMP images
image_directory = '../car_image/sparse_traffic/'

# Get a list of all BMP files in the directory
bmp_files = glob.glob(image_directory + '/*.jpg')
print(bmp_files)
images = []
images2view = []


for bmp_file in bmp_files:
    print(bmp_file)
    im = cv2.imread(bmp_file)
    im = cv2.resize(im, (416,416), interpolation= cv2.INTER_LINEAR)
    images2view.append(im)
    im = np.flip(im,axis=-1)
    lead_zeros = np.zeros((416,416,1),dtype=np.uint8)
    images.append(np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8))



size = 71825*4

#Create Shared Memory
with open('shared.mem', "wb") as f:
        f.seek(size)  # Go to the last byte
        f.write(b"\0")  # Write a single byte to ensure the file is the correct size


#Tell inference we are ready!

sem = posix_ipc.Semaphore("/CoreDLA_ready_for_streaming",flags=posix_ipc.O_CREAT, mode=0o644, initial_value=0);

firstTime = True

while True:

    try:
        sem.acquire(0)
    except:
        if (firstTime):
          firstTime = False
          print("Waiting for streaming_inference_app to become ready.")
    else:
        sem.release()
        break


    time.sleep(0.1)
sem.close()


#Get Shared memory
offset = 0
mmap_file = os.open('shared.mem', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
output_map = np.frombuffer(mem, np.float32, size >> 2)

output_map = np.reshape(output_map, (1,425,13,13))

#Stream Images

count = 0

while True:


    nwritten = 0
    image2view = images2view[count % len(images)]
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(images[count % len(images)].tobytes())
    print(count, nwritten)
    count += 1
