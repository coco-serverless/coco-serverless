#!/bin/bash

file_size_mb=100

block_count=$file_size_mb

for dir in $(find / -maxdepth 1 -type d ! -name "proc" ! -name "sys" ! -name "tmp" ! -path "/")
do
    if [ -w "$dir" ]; then
        file_path="$dir/random_100mb_file"
        echo "Creating a 100MB random file in $dir"
        dd if=/dev/urandom of="$file_path" bs=1M count=$block_count status=none
    else
        echo "Skipping $dir, no write permission."
    fi
done

echo "File creation complete."
