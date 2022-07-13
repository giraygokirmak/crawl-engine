FROM arm64v8/ubuntu:focal
RUN apt update 
RUN DEBIAN_FRONTEND=noninteractive TZ=Europe/Istanbul apt-get install -yq tzdata python3 python3-dev libmysqlclient-dev python3-pip firefox firefox-geckodriver && \
    ln -fs /usr/share/zoneinfo/Europe/Istanbul /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata
RUN python3 -m pip install lxml retry selenium mysqlclient bs4 pandas requests
ADD src /src
ENTRYPOINT [ "python3","-c","from src.engine import Engine; Engine().update_rates()"]
