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

# Copy Quartus license file into the image
# Adjust the path if the license file is beside your Dockerfile
COPY License.dat /home/${USER}/License.dat

# Fix ownership so the ${USER} user can read it
RUN chown ${USER}:${USER} /home/${USER}/License.dat

# Append Altera/Intel FPGA tool paths to ${USER} user's PATH
RUN echo 'export PATH=$PATH:/opt/altera/fpga_ai_suite/ubuntu/dla/bin:/opt/altera/riscfree/RiscFree:/opt/altera/riscfree/toolchain/riscv32-unknown-elf/bin:/opt/altera/quartus/bin:/opt/altera/niosv/bin:/opt/altera/qsys/bin' >> /home/${USER}/.bashrc && \
    echo 'export LM_LICENSE_FILE=/home/${USER}/License.dat' >> /home/${USER}/.bashrc && \
    chown ${USER}:${USER} /home/${USER}/.bashrc

# Create user Quartus config directory and copy quartus.ini
COPY quartus.ini /home/${USER}/.altera.quartus/quartus.ini
RUN chown -R ${USER}:${USER} /home/${USER}/.altera.quartus

# Make XRDP launch Xfce
RUN echo "startxfce4" > /home/${USER}/.xsession && chown ${USER}:${USER} /home/${USER}/.xsession

# Tweak xrdp to allow non-console users
RUN sed -i 's/^\s*#\?\s*allowed_users=.*/allowed_users=anybody/' /etc/X11/Xwrapper.config || true

# Expose RDP
EXPOSE 3389

# Start services (Xvnc via xrdp-sesman)
CMD ["/bin/bash","-lc","service dbus start && /usr/sbin/xrdp-sesman && /usr/sbin/xrdp && tail -F /var/log/xrdp.log /var/log/xrdp-sesman.log"]
