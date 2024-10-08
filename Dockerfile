FROM ubuntu:jammy

RUN apt-get update
RUN apt-get install -y unzip curl libcurl4 libssl3
# https://www.minecraft.net/en-us/download/server/bedrock
RUN curl https://minecraft.azureedge.net/bin-linux/bedrock-server-1.21.20.03.zip --output bedrock-server.zip
RUN unzip bedrock-server.zip -d bedrock-server
RUN chmod +x bedrock-server/bedrock_server
RUN rm bedrock-server.zip

WORKDIR /bedrock-server
ENV LD_LIBRARY_PATH=.
CMD ./bedrock_server
 
