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
# Width and Height of the DMA Frame
uio_map[2] = 28 
uio_map[3] = 28

uio_fp[16] = 1.0
uio_fp[17] = 1.0
uio_fp[18] = 1.0
uio_fp[32] = -103.94
uio_fp[33] = -116.78
uio_fp[34] = -123.68


size = 40

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

#Stream Images

count = 0

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Set the address and port of the receiver
server_address = ('192.168.0.33', 12345)

# Create a UDP socket
rxsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
local_address = ('192.168.0.180', 12345)
rxsock.bind(local_address)

while True:

    print("\n\r#######################################################################\n\r")


    frame, _ = rxsock.recvfrom(65536)
    frame = np.frombuffer(frame, dtype=np.uint8).reshape(28,28,3)
    image2view = frame
    im = frame
    print(im.shape)
    lead_zeros = np.zeros((28,28,1),dtype=np.uint8)
    im = np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8)

    nwritten = 0
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(im.tobytes())
    print(count, nwritten)
    count += 1
    time.sleep(0.1)
    print((output_map))
    print(np.argmax(output_map))
    time.sleep(0.1)
    
