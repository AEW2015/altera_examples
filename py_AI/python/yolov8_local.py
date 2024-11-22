import posix_ipc
import cv2
import glob
import numpy as np
import time
import os
import mmap


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
uio_map[2] = 224
uio_map[3] = 224

uio_fp[16] = 1.0
uio_fp[17] = 1.0
uio_fp[18] = 1.0
uio_fp[32] = 0
uio_fp[33] = 0
uio_fp[34] = 0

#Get Images

# Specify the directory containing the BMP images
image_directory = '../yolov8n_test/'

# Get a list of all BMP files in the directory
bmp_files = glob.glob(image_directory + '/*.jpg')

images = []

def letterbox(image, target_size=(640, 640), color=(114, 114, 114)):
    original_height, original_width = image.shape[:2]
    target_width, target_height = target_size

    # Calculate the scale factor and new width and height with aspect ratio preserved
    scale = min(target_width / original_width, target_height / original_height)
    new_width = int(original_width * scale)
    new_height = int(original_height * scale)

    # Resize the image with the aspect ratio maintained
    resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

    # Create a new image with the target size, filled with the padding color
    padded_image = np.full((target_height, target_width, 3), color, dtype=np.uint8)

    # Calculate top-left coordinates to center the resized image on the padding
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2

    # Place the resized image onto the padded image
    padded_image[y_offset:y_offset + new_height, x_offset:x_offset + new_width] = resized_image

    return padded_image


for bmp_file in bmp_files:
    im = cv2.imread(bmp_file)
    im = letterbox(im, target_size=(224,224))
    im = np.flip(im,axis=-1)
    lead_zeros = np.zeros((224,224,1),dtype=np.uint8)
    images.append(np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8))


#Create Shared Memory
with open('shared.mem', "wb") as f:
        f.seek(4000)  # Go to the last byte
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
size = 4000
offset = 0
mmap_file = os.open('shared.mem', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
output_map = np.frombuffer(mem, np.float32, size >> 2)


with open("imagenet-classes.txt") as file:
    lines = [line.rstrip() for line in file]

#Stream Images

count = 0


infer_semaphore = posix_ipc.Semaphore("/CoreDLA_infer",flags=posix_ipc.O_CREAT, mode=0o644, initial_value=0);
post_semaphore = posix_ipc.Semaphore("/CoreDLA_post",flags=posix_ipc.O_CREAT, mode=0o644, initial_value=0);

for image in images:

    #timer_semaphore.release()
    nwritten = 0
    
    start_time = time.perf_counter()
    # Start time
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(image.tobytes())
    
    dma_time = time.perf_counter()
    infer_semaphore.acquire()
    infer_time = time.perf_counter()
    
    post_semaphore.acquire()
    # End time
    end_time = time.perf_counter()
    # Calculate elapsed time
    elapsed_time = dma_time - start_time
    print(f"DMA execution time: {elapsed_time:.6f} seconds")
    elapsed_time = infer_time - dma_time
    print(f"Inference execution time: {elapsed_time:.6f} seconds")
    elapsed_time = end_time - infer_time
    print(f"Post Process execution time: {elapsed_time:.6f} seconds")

    
    #print(count, nwritten)
    count += 1
    
    #print(output_map[0:1000])
    top_5_indices = np.argsort(output_map)[-5:][::-1]
    
    print(top_5_indices)
    for i in top_5_indices:
        print(output_map[i],lines[i])
