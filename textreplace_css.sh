#! /bin/bash

echo "$1"
sed --in-place "s/\/wp-content\/themes\/eisai-child\/assets\//\/assets\//g" "$1"