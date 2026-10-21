FROM locustio/locust:2.43.4

WORKDIR /loadtest
COPY locustfile.py config.py /loadtest/

ENTRYPOINT ["locust"]
