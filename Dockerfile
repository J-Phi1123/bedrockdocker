FROM ubuntu:bionic

RUN add-apt-repository ppa:ubuntu-toolchain-r/test
RUN apt-get update
RUN apt-get install -y unzip curl libcurl4 libssl1.0.0 gcc-9 licstdc++6
# https://www.minecraft.net/en-us/download/server/bedrock
RUN curl https://minecraft.azureedge.net/bin-linux/bedrock-server-1.20.30.02.zip --output bedrock-server.zip
RUN unzip bedrock-server.zip -d bedrock-server
RUN chmod +x bedrock-server/bedrock_server
RUN rm bedrock-server.zip

WORKDIR /bedrock-server
ENV LD_LIBRARY_PATH=.
CMD ./bedrock_server
 
