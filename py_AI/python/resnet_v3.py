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
uio_map[2] = 224
uio_map[3] = 224

uio_fp[16] = 1.0
uio_fp[17] = 1.0
uio_fp[18] = 1.0
uio_fp[32] = -103.94
uio_fp[33] = -116.78
uio_fp[34] = -123.68

#Get Images

# Specify the directory containing the BMP images
image_directory = '../resnet-50-tf/sample_images/'

# Get a list of all BMP files in the directory
bmp_files = glob.glob(image_directory + '/*.bmp')

images = []
images2view = []

for bmp_file in bmp_files:
    im = cv2.imread(bmp_file)
    im = cv2.resize(im, (224,224), interpolation= cv2.INTER_LINEAR)
    images2view.append(im)
    im = np.flip(im,axis=-1)
    lead_zeros = np.zeros((224,224,1),dtype=np.uint8)
    images.append(np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8))


#Create Shared Memory
with open('shared.mem', "wb") as f:
        f.seek(63)  # Go to the last byte
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
size = 40
offset = 0
mmap_file = os.open('shared.mem', os.O_RDWR | os.O_SYNC)
mem = mmap.mmap(mmap_file, size,
                mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE,
                offset=offset)
os.close(mmap_file)
output_map = np.frombuffer(mem, np.uint32, size >> 2)

#Get labels
with open("imagenet-classes.txt") as file:
    lines = [line.rstrip() for line in file]


#Stream Images

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Set the address and port of the receiver
server_address = ('192.168.0.33', 12345)



count = 0

while True:


    nwritten = 0
    image2view = images2view[count % len(images)]
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(images[count % len(images)].tobytes())
    print(count, nwritten)
    count += 1
    
    
    
    time.sleep(0.5)
    print(output_map)
    label = lines[output_map[0]-1]
    print(label)
    
    # Add text to the image
    position = (10, 180)  # Bottom-left corner of the text
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.5
    color = (255, 255, 255)  # White color in BGR
    thickness = 4
    cv2.putText(image2view, label, position, font, font_scale, color, thickness)
    
    # Encode the frame as JPEG
    _, encoded_frame = cv2.imencode('.jpeg', image2view)

    # Send the encoded frame over UDP
    sock.sendto(encoded_frame, server_address)

sock.close()
