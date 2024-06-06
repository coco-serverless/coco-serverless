#!/bin/bash

fio_job_file="fio_read_jobfile.fio"
target_file_name_1="random_75mb_file_1"
target_file_name_2="random_75mb_file_2"

echo "" > "$fio_job_file"

for dir in $(find / -maxdepth 1 -type d ! -name "proc" ! -name "sys" ! -name "tmp" ! -path "/")
do
    file_path="$dir/$target_file_name_1"
    if [ -f "$file_path" ]; then
        echo "[job_$dir]" >> "$fio_job_file"
        echo "filename=$file_path" >> "$fio_job_file"
        echo "rw=read" >> "$fio_job_file"
        echo "ioengine=libaio" >> "$fio_job_file"
        echo "iodepth=1" >> "$fio_job_file"
        echo "size=75m" >> "$fio_job_file"
        echo "direct=0" >> "$fio_job_file"
        echo "thinktime=200" >> "$fio_job_file"
        echo "blocksize=4k" >> "$fio_job_file"
        echo "numjobs=1" >> "$fio_job_file"
        echo "group_reporting" >> "$fio_job_file"
    fi

    file_path="$dir/$target_file_name_2"
    if [ -f "$file_path" ]; then
        echo "[job_$dir]" >> "$fio_job_file"
        echo "filename=$file_path" >> "$fio_job_file"
        echo "rw=read" >> "$fio_job_file"
        echo "ioengine=libaio" >> "$fio_job_file"
        echo "iodepth=1" >> "$fio_job_file"
        echo "size=75m" >> "$fio_job_file"
        echo "direct=0" >> "$fio_job_file"
        echo "thinktime=200" >> "$fio_job_file"
        echo "blocksize=4k" >> "$fio_job_file"
        echo "numjobs=1" >> "$fio_job_file"
        echo "group_reporting" >> "$fio_job_file"
    fi
done

echo "FIO job file creation complete."