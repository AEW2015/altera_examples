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

anchors = np.array([[0.57273, 0.677385], 
                    [1.87446, 2.06253], 
                    [3.33843, 5.47434], 
                    [7.88282, 3.52778], 
                    [9.77052, 9.16828]])

grid_size = 416/13

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Set the address and port of the receiver
server_address = ('192.168.0.33', 12345)

# Create a UDP socket
rxsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
local_address = ('192.168.0.94', 12345)
rxsock.bind(local_address)

while True:

    print("\n\r#######################################################################\n\r")


    frame, _ = rxsock.recvfrom(65536)
    frame = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), 1)
    image2view = frame
    im = np.flip(frame,axis=-1)
    lead_zeros = np.zeros((416,416,1),dtype=np.uint8)
    im = np.concatenate((lead_zeros,im),axis=-1,dtype=np.uint8)

    nwritten = 0
    with open("/dev/msgdma_stream0", "wb+", buffering=0) as f:
        nwritten = f.write(im.tobytes())
    print(count, nwritten)
    count += 1
    time.sleep(0.1)
    
    for x in range(5):
        for j in range (13):
            for k in range(13):
                if output_map[0,x*85+4,j,k] > 0.4:
                    conf    = output_map[0,x*85+4,j,k]
                    car_c   = output_map[0,x*85+7,j,k]
                    x_pred  = output_map[0,x*85,j,k]
                    y_pred  = output_map[0,x*85+1,j,k]
                    t_w     = output_map[0,x*85+2,j,k]
                    t_h     = output_map[0,x*85+3,j,k]
                    #print(x_pred, y_pred, t_w, t_h)
                    x_sigm=sigmoid(x_pred)
                    y_sigm=sigmoid(y_pred)
                    #print(x_sigm,y_sigm)
                    bx = (k +x_sigm)*grid_size
                    by = (j +y_sigm)*grid_size
                    bw = anchors[x,0] * np.exp(t_w) * grid_size
                    bh = anchors[x,1] * np.exp(t_h) * grid_size

                    txt = "\n\r-> Conf:{0:1.3f} Car:{1:1.3f} X:{2:0.0f} Y:{3:0.0f} W:{4:0.0f} H:{5:0.0f} Anchor: {6} \n\r"
                    print(txt.format(conf,car_c,bx,by,bw,bh,x))
                    top_left_x = int(bx - bw / 2)
                    top_left_y = int(by - bh / 2)
                    bottom_right_x = int(bx + bw / 2)
                    bottom_right_y = int(by + bh / 2)

                    # Draw the bounding box on the resized image (color: green, thickness: 2)
                    cv2.rectangle(image2view, (top_left_x, top_left_y), (bottom_right_x, bottom_right_y), (0, 255*(conf), 255*(1-conf)), 2)
    
 
    _, encoded_frame = cv2.imencode('.jpeg', image2view,[cv2.IMWRITE_JPEG_QUALITY, 50])
    # Send the encoded frame over UDP
    sock.sendto(encoded_frame, server_address)



