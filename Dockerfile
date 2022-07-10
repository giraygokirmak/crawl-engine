FROM arm64v8/ubuntu:focal
RUN apt update 
RUN DEBIAN_FRONTEND=noninteractive TZ=Europe/Istanbul apt-get install -yq tzdata python3 python3-pip firefox firefox-geckodriver selenium pymongo bs4 pandas requests dnspython && \
    ln -fs /usr/share/zoneinfo/Europe/Istanbul /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata
ENTRYPOINT [ "python3","-c","from engine import Engine; Engine().update_rates()"]
