FROM alterafpga/fpgaaisuite-v2025.3:quartus

ENV DEBIAN_FRONTEND=noninteractive

# --- RiscFree silent install to /opt/altera/riscfree ---
# Pass the URL at build time or keep the default below
ARG RF_URL="https://cdrdv2.intel.com/v1/dl/getContent/865546/865563?filename=RiscFreeSetup-25.3.0.109-linux.run"

# Download and install silently (install4j: -q unattended, -dir sets prefix)
RUN apt-get update && apt-get install -y curl ca-certificates && \
    mkdir -p /opt/altera && \
    curl -L "$RF_URL" -o /tmp/RiscFreeSetup.run && \
    chmod +x /tmp/RiscFreeSetup.run && \
    /tmp/RiscFreeSetup.run --accept_eula 1 --mode unattended --installdir /opt/altera/ && \
    rm -f /tmp/RiscFreeSetup.run

# --- Questa silent install to /opt/altera ---
ARG QUESTA_URL="https://downloads.intel.com/akdlm/software/acdsinst/25.3.1/100/ib_installers/QuestaSetup-25.3.1.100-linux.run"

RUN curl -L "$QUESTA_URL" -o /tmp/QuestaSetup.run && \
    chmod +x /tmp/QuestaSetup.run && \
    /tmp/QuestaSetup.run --accept_eula 1 --mode unattended --installdir /opt/altera/ && \
    rm -f /tmp/QuestaSetup.run


# Desktop + XRDP + VNC backend + basics
RUN apt update && apt install -y \
    xfce4 xfce4-terminal \
    xrdp tigervnc-standalone-server dbus-x11 \
    sudo nano \
 && rm -rf /var/lib/apt/lists/*

# Create a normal user
ARG USER=dev
ARG PASS=dev
RUN useradd -m -s /bin/bash ${USER} \
 && echo "${USER}:${PASS}" | chpasswd \
 && adduser ${USER} sudo

RUN groupadd -f plugdev && usermod -aG plugdev dev

# Copy Quartus license file into the image
# Adjust the path if the license file is beside your Dockerfile
COPY ../License.dat /home/${USER}/License.dat

# Fix ownership so the ${USER} user can read it
RUN chown ${USER}:${USER} /home/${USER}/License.dat

# Append Altera/Intel FPGA tool paths to ${USER} user's PATH
RUN echo 'export PATH=$PATH:'\
'/opt/altera/fpga_ai_suite/ubuntu/dla/bin:'\
'/opt/altera/riscfree/RiscFree:'\
'/opt/altera/riscfree/toolchain/riscv32-unknown-elf/bin:'\
'/opt/altera/quartus/bin:'\
'/opt/altera/niosv/bin:'\
'/opt/altera/qsys/bin:'\
'/opt/altera/questa_fse/bin/' >> /home/${USER}/.bashrc && \
    echo 'export LM_LICENSE_FILE=/home/${USER}/License.dat' >> /home/${USER}/.bashrc && \
    echo 'export SALT_LICENSE_SERVER=$LM_LICENSE_FILE' >> /home/${USER}/.bashrc && \
    chown ${USER}:${USER} /home/${USER}/.bashrc

# Create user Quartus config directory and copy quartus.ini
#COPY quartus.ini /home/${USER}/.altera.quartus/quartus.ini
#RUN chown -R ${USER}:${USER} /home/${USER}/.altera.quartus

# Install Python and development tools
RUN apt-get update && apt-get install -y \
    python3 python3-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

# Setup JupyterLab virtual environment for dev user
RUN mkdir -p /home/${USER}/venv-jlab && \
    chown ${USER}:${USER} /home/${USER}/venv-jlab

USER ${USER}
RUN python3 -m venv /home/${USER}/venv-jlab && \
    /home/${USER}/venv-jlab/bin/pip install --upgrade pip && \
    /home/${USER}/venv-jlab/bin/pip install jupyterlab ipykernel

#dockRUN echo 'source /home/${USER}/venv-jlab/bin/activate' >> /home/${USER}/.bashrc

USER root

# Make XRDP launch Xfce
RUN echo "startxfce4" > /home/${USER}/.xsession && chown ${USER}:${USER} /home/${USER}/.xsession

# Tweak xrdp to allow non-console users
RUN sed -i 's/^\s*#\?\s*allowed_users=.*/allowed_users=anybody/' /etc/X11/Xwrapper.config || true

# Expose RDP
EXPOSE 3389

# Start services (Xvnc via xrdp-sesman)
CMD ["/bin/bash", "-c", "\
rm -f /var/run/dbus/pid /var/run/xrdp/xrdp-sesman.pid; \
service dbus start && \
echo 'Step 1' && \
/usr/sbin/xrdp-sesman && \
echo 'Step 2' && \
service xrdp restart && \
echo 'XRDP started successfully. Connect via RDP on port 3389.' && \
tail -F /var/log/xrdp.log /var/log/xrdp-sesman.log"]
