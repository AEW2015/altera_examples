# Rapid Prototyping FPGA AI with Python

Use Python to:
* Interacte with FPGA AI SoC Streaming Interface
* Better controls over data input (video, web)
* React to AI inference with complex outputs

## TODOs

* add Semaphore for Inference done
* add Python class for UIO2/layout_transform
* add layers.txt option
* add camera input option
* add udp output for quick viewing
* add cli arguments
* add list of tested OpenVino examples

## Guide

* Using wic image in release
* do normal resnet-50-tf flow in Agilex 7 Demo
* from `~/app` run `python3 load_img.py` with `./run_inference_stream.sh`

### Optional SD Card build

* `cd $COREDLA_WORK/runtime` 
* `mkdir repos; cd repos`
* `git clone https://github.com/openembedded/meta-openembedded`
* `cd meta-openembedded`
* `git checkout da9063bdf`
* Update $COREDLA_ROOT/dla/hps/ed4/yocto/run-build.sh
``` 
    bitbake-layers add-layer $COREDLA_WORK/runtime/repos/meta-openembedded/meta-oe && \
    bitbake-layers add-layer $COREDLA_WORK/runtime/repos/meta-openembedded/meta-python && \
    bitbake-layers add-layer $COREDLA_WORK/runtime/repos/meta-openembedded/meta-devtools && \
    bitbake-layers add-layer $COREDLA_WORK/runtime/repos/meta-openembedded/meta-networking && \
    bitbake-layers add-layer $COREDLA_WORK/runtime/repos/meta-openembedded/meta-multimedia && \
```
* Update $COREDLA_ROOT/dla/hps/ed4/yocto/meta-intel-fpga-coredla/recipes-core/images/coredla-image.bb
```
# ADD YOUR MODULE RECIPE(S) HERE
IMAGE_INSTALL:append = " \
	${VIRTUAL-RUNTIME_dev_manager} \
	${VIRTUAL-RUNTIME_init_manager} \
	${VIRTUAL-RUNTIME_initscripts} \
	${VIRTUAL-RUNTIME_login_manager} \
	packagegroup-core-ssh-openssh \
	mtd-utils-ubifs \
	devmem2 \
	i2c-tools \
	update-alternatives-opkg \
	setmacaddress \
	strace \
	python3-pip \
	python3-opencv \
	python3-posix-ipc \
	libcamera \
	libusb-compat \
	libuvc \
	libftdi \
	gdbserver \
	hostnamemac \
	avahi-daemon \
	avahi-autoipd \
	msgdma-userio \
	uio-devices \
	kernel-modules \
	"
```
* Replace $COREDLA_WORK/streaming/streaming_inference_app/streaming_inference_app.cpp 
* Build SD Card image with Demo Agilex 7 SoC sof file
```
cd $COREDLA_WORK/runtime
./create_hps_image.sh \
    -f $COREDLA_WORK/demo/ed4/agx7_soc_s2m/bitstreams/AGX7_Performance \
    -o <output_dir> -u \
    -m agilex7_dk_si_agi027fa
```