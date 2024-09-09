import posix_ipc
import cv2
import glob
import numpy as np
import time
import os
import mmap

size = 0x1000
offset = 0

mmap_file = os.open('/dev/uio2', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
uio_map = np.frombuffer(mem, np.uint32, size >> 2)

uio_map[0] = 1
time.sleep(0.1)
uio_map[0] = 0
uio_map[1] = 32
uio_map[2] = 224
uio_map[3] = 224
uio_map[16] = 0x3F800000
uio_map[17] = 0x3F800000
uio_map[18] = 0x3F800000
uio_map[32] = 0xC2D1EB86
uio_map[33] = 0xC2E9D1EB
uio_map[34] = 0xC2F7AE28


with open('shared.mem', "wb") as f:
        f.seek(63)  # Go to the last byte
        f.write(b"\0")  # Write a single byte to ensure the file is the correct size


# Specify the directory containing the BMP images
image_directory = '../resnet-50-tf/sample_images/'

# Get a list of all BMP files in the directory
bmp_files = glob.glob(image_directory + '/*.bmp')

images = []

for bmp_file in bmp_files:
    im = cv2.imread(bmp_file)
    im = cv2.resize(im, (224,224), interpolation= cv2.INTER_LINEAR)
    im = np.flip(im,axis=-1)
    lead_zeros = np.zeros((224,224,1),dtype=np.uint8)
    images.append(np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8))

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

size = 40
offset = 0
mmap_file = os.open('shared.mem', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
output_map = np.frombuffer(mem, np.uint32, size >> 2)

count = 0

while True:


    nwritten = 0
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(images[count % len(images)].tobytes())
    print(count, nwritten)
    count += 1
    
    time.sleep(0.5)
    print(output_map)
    time.sleep(0.5)

