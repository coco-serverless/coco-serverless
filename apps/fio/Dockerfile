
FROM alpine:latest

RUN apk update && apk add fio nano

COPY benchmark.sh .
COPY file_gen_?.sh .

RUN chmod +x benchmark.sh && chmod +x file_gen_1.sh && chmod +x file_gen_2.sh

RUN source file_gen_1.sh

RUN source file_gen_2.sh

RUN source benchmark.sh

#CMD find / \( -path /proc -o -path /sys \) -prune -o -type f -exec grep "test" {} +
#CMD tail -f /dev/null
#CMD while true; do sleep 3600; done
CMD fio fio_read_jobfile.fio
